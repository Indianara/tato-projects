#!/usr/bin/env python3
"""
Prestador Mais Próximo — Aplicativo CLI.

Uso:
    python run.py                       # pergunta o caminho do XLSX
    python run.py camuino/arquivo.xlsx  # processa direto
    Arraste um .xlsx sobre o .app       # mac啱s py2app

Pipeline completa:
  1. Converte XLSX → CSV
  2. Normaliza dados
  3. Geocodifica CEPs (AwesomeAPI + cache)
  4. Calcula distâncias (Haversine + OSRM)
  5. Gera resultado_final.csv
"""

import json
import sys
import time
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from src.normalizacao import (
    _safe_str,
    mapear_pendente,
    normalizar_prestadores,
    unificar_associados,
    salvar_csv,
)
from src.geocoder import batch_geocode
from src.distance import find_nearest

FILES_DIR = BASE_DIR / "Files"
CACHE_DIR = BASE_DIR / "cache"
OUTPUT_DIR = BASE_DIR / "output"

AGENDAMENTOS_FILE = FILES_DIR / "pendente_para_instalacao.csv"
PRESTADORES_FILE = FILES_DIR / "Base Prestadores.csv"
CEP_CORRECOES_FILE = FILES_DIR / "CEPs_Corrigidos.csv"
GEO_CACHE_FILE = CACHE_DIR / "geocode_cache.json"

OUTPUT_ASSOCIADOS = OUTPUT_DIR / "associados_normalizados.csv"
OUTPUT_PRESTADORES = OUTPUT_DIR / "prestadores_normalizados.csv"
OUTPUT_FINAL = OUTPUT_DIR / "resultado_final.csv"
OUTPUT_SEM_COORD = OUTPUT_DIR / "associados_sem_coordenada.csv"
OUTPUT_PREST_SEM_COORD = OUTPUT_DIR / "prestadores_sem_coordenada.csv"

TOP_N = 3
PRE_FILTER = 15
OSRM_DELAY = 0.5

COLUNAS_PRESTADOR_SUFIXOS = [
    "Nome", "Nome_Legal", "CNPJ_CPF", "Tipo_Fornecedor", "Classificacao",
    "Endereco", "Cidade", "UF", "CEP", "Distancia_km",
    "Contato", "Telefone", "Telefone_2", "Email", "Tipos_Veiculos", "Observacao",
]


def build_fieldnames(vehicle_columns):
    fieldnames = list(vehicle_columns)
    for i in range(1, TOP_N + 1):
        for s in COLUNAS_PRESTADOR_SUFIXOS:
            fieldnames.append(f"Prestador_{i}_{s}")
    return fieldnames


def fill_prestador_row(row, i, p):
    mappings = [
        ("Nome", "nome"), ("Nome_Legal", "nome_legal"),
        ("CNPJ_CPF", "cnpj_cpf"), ("Tipo_Fornecedor", "tipo_fornecedor"),
        ("Classificacao", "classificacao"), ("Endereco", "endereco"),
        ("Cidade", "cidade"), ("UF", "uf"),
        ("CEP", "cep"), ("Distancia_km", "road_km"),
        ("Contato", "contato"), ("Telefone", "telefone"),
        ("Telefone_2", "telefone_2"), ("Email", "email"),
        ("Tipos_Veiculos", "tipos_veiculos"), ("Observacao", "observacao"),
    ]
    for suf, key in mappings:
        row[f"Prestador_{i}_{suf}"] = p.get(key, "")


def clear_prestador_row(row, i):
    for s in COLUNAS_PRESTADOR_SUFIXOS:
        row[f"Prestador_{i}_{s}"] = ""


def build_candidates(df_prest, geo, coord_manuais=None):
    candidates = []
    for _, row in df_prest.iterrows():
        cep = _safe_str(row.get("cep_normalizado"))
        nome_legal = _safe_str(row.get("nome"))
        nome_fantasia = _safe_str(row.get("nome_fantasia"))
        lat = lng = None
        if coord_manuais:
            chave = nome_legal.upper()
            manual = coord_manuais.get(chave)
            if not manual:
                chave = nome_fantasia.upper()
                manual = coord_manuais.get(chave)
            if manual:
                lat, lng = manual
        if lat is None:
            coords = geo.get(cep)
            if coords:
                lat = coords["lat"]
                lng = coords["lng"]
        if lat is None:
            continue
        candidates.append({
            "lat": lat, "lng": lng,
            "nome": nome_fantasia or nome_legal,
            "nome_legal": nome_legal,
            "cnpj_cpf": _safe_str(row.get("cpf_cnpj")),
            "cep": cep,
            "cidade": _safe_str(row.get("cidade")),
            "uf": _safe_str(row.get("uf_normalizado")),
            "telefone": _safe_str(row.get("telefone_1")),
            "telefone_2": _safe_str(row.get("telefone_2")),
            "email": _safe_str(row.get("email")),
            "contato": _safe_str(row.get("contato")),
            "tipo_fornecedor": _safe_str(row.get("tipo_fornecedor")),
            "classificacao": _safe_str(row.get("classificacao")),
            "tipos_veiculos": _safe_str(row.get("tipos_veiculos")),
            "observacao": _safe_str(row.get("observacao")),
            "endereco": _safe_str(row.get("endereco_completo")),
        })
    return candidates


def carregar_correcoes_cep(path):
    correcoes = {}
    coords = {}
    if not path.exists():
        return correcoes, coords
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    for _, row in df.iterrows():
        nome = _safe_str(row.get("nome")).upper()
        if not nome:
            continue
        lat = _safe_str(row.get("lat"))
        lon = _safe_str(row.get("lon"))
        if lat and lon:
            try:
                coords[nome] = (float(lat), float(lon))
            except ValueError:
                pass
        cep = row.get("Cep_Correto", "")
        if isinstance(cep, str):
            cep = "".join(c for c in cep if c.isdigit())
            if len(cep) == 8:
                correcoes[nome] = cep
    return correcoes, coords


def converter_xlsx(xlsx_path):
    print(f"\n[0/6] Convertendo XLSX → CSV...")
    print(f"  Arquivo: {xlsx_path}")
    df = pd.read_excel(xlsx_path, engine="openpyxl")
    df.columns = df.iloc[0]
    df = df.iloc[1:].reset_index(drop=True)
    df.to_csv(AGENDAMENTOS_FILE, index=False, encoding="utf-8-sig")
    print(f"  {len(df)} registros convertidos → {AGENDAMENTOS_FILE.name}")
    return df


def processar():
    print("=" * 60)
    print("  Prestador Mais Proximo — Pipeline Completa")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. Normalizacao ──
    print("\n[1/6] Normalizando dados...")
    df_agend = mapear_pendente(AGENDAMENTOS_FILE)
    df_pend = pd.DataFrame()
    df_assoc = unificar_associados(df_agend, df_pend)
    salvar_csv(df_assoc, OUTPUT_ASSOCIADOS)

    print("\n  Normalizando prestadores...")
    correcoes, coord_manuais = carregar_correcoes_cep(CEP_CORRECOES_FILE)
    df_prest = normalizar_prestadores(PRESTADORES_FILE, correcoes)
    salvar_csv(df_prest, OUTPUT_PRESTADORES)

    # ── 2. Geocoding ──
    print("\n[2/6] Geocodificando CEPs...")
    if GEO_CACHE_FILE.exists():
        with open(GEO_CACHE_FILE, "r", encoding="utf-8") as f:
            geo = json.load(f)
    else:
        geo = {}
    print(f"  Cache atual: {len(geo)} CEPs com coordenadas")

    entries = []
    for _, row in df_assoc.iterrows():
        cep = _safe_str(row.get("cep"))
        if cep and not geo.get(cep):
            entries.append({
                "cep": cep,
                "city": _safe_str(row.get("cidade")),
                "state": _safe_str(row.get("estado")),
                "endereco": _safe_str(row.get("endereco_completo")),
                "bairro": _safe_str(row.get("bairro")),
            })
    for _, row in df_prest.iterrows():
        cep = _safe_str(row.get("cep_normalizado"))
        if cep and not geo.get(cep):
            entries.append({
                "cep": cep,
                "city": _safe_str(row.get("cidade")),
                "state": _safe_str(row.get("uf_normalizado")),
                "endereco": _safe_str(row.get("endereco_completo")),
                "bairro": _safe_str(row.get("bairro")),
            })

    unicos = len({e["cep"] for e in entries})
    if entries:
        print(f"  {unicos} CEPs unicos novos para geocodificar...")
        batch_geocode(entries, verbose=True)
        with open(GEO_CACHE_FILE, "r", encoding="utf-8") as f:
            geo = json.load(f)
        print(f"  Cache atualizado: {len(geo)} CEPs total")
    else:
        print("  Todos os CEPs ja estao no cache")

    # ── 3. Separar veiculos ──
    print("\n[3/6] Separando veiculos com coordenada...")
    df_assoc["cep"] = df_assoc["cep"].fillna("")

    def has_coords(cep):
        return bool(cep) and bool(geo.get(cep))

    df_com = df_assoc[df_assoc["cep"].map(has_coords)].copy()
    df_sem = df_assoc[~df_assoc["cep"].map(has_coords)].copy()
    print(f"  Com coordenada: {len(df_com)} veiculos")
    print(f"  Sem coordenada: {len(df_sem)} veiculos")

    if not df_sem.empty:
        salvar_csv(df_sem, OUTPUT_SEM_COORD)

    if df_com.empty:
        print("\n  Nenhum veiculo com coordenada. Encerrando.")
        return

    # ── 4. Prestadores sem coordenada ──
    print("\n[4/6] Prestadores sem coordenada...")
    mask = ~df_prest["cep_normalizado"].fillna("").map(has_coords)
    df_prest_sem = df_prest[mask].copy()
    if not df_prest_sem.empty:
        salvar_csv(df_prest_sem, OUTPUT_PREST_SEM_COORD)
        print(f"  {len(df_prest_sem)} prestadores sem coordenada")
    else:
        print("  Todos os prestadores tem coordenada")

    # ── 5. Build candidates ──
    print("\n[5/6] Construindo lista de candidatos...")
    candidates = build_candidates(df_prest, geo, coord_manuais)
    print(f"  {len(candidates)} prestadores com coordenada")
    if not candidates:
        print("\n  Nenhum prestador com coordenada. Encerrando.")
        return

    # ── 6. Processar distancias ──
    print("\n[6/6] Calculando distancias via Haversine + OSRM...")
    vehicle_columns = [c for c in df_com.columns if not c.startswith("_")]
    fieldnames = build_fieldnames(vehicle_columns)

    from tqdm import tqdm

    with open(OUTPUT_FINAL, "w", newline="", encoding="utf-8-sig") as f:
        import csv
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        for _, carro in tqdm(df_com.iterrows(), total=len(df_com), desc="  Processando"):
            cep = str(carro.get("cep", "") or "")
            row = {col: _safe_str(carro.get(col)) for col in vehicle_columns}
            nearest = []
            coords = geo.get(cep)
            if coords:
                nearest = find_nearest(
                    origin_lat=coords["lat"],
                    origin_lng=coords["lng"],
                    candidates=candidates,
                    top_n=TOP_N,
                    pre_filter=PRE_FILTER,
                    osrm_delay=OSRM_DELAY,
                )
            for i in range(1, TOP_N + 1):
                if i <= len(nearest):
                    fill_prestador_row(row, i, nearest[i - 1])
                else:
                    clear_prestador_row(row, i)
            writer.writerow(row)
            f.flush()

    print(f"\n  Resultado salvo: {OUTPUT_FINAL.name}")

    # ── Fim ──
    print("\n" + "=" * 60)
    print("  PIPELINE CONCLUIDA COM SUCESSO!")
    print(f"  {len(df_com)} veiculos processados")
    print(f"  {len(df_sem)} veiculos sem coordenada")
    print(f"  {len(candidates)} prestadores disponiveis")
    print("=" * 60)


def main():
    # Detecta se um arquivo foi passado (CLI ou arrastado no .app)
    if len(sys.argv) > 1:
        xlsx_path = Path(sys.argv[1])
        if not xlsx_path.exists():
            print(f"Erro: arquivo nao encontrado: {xlsx_path}")
            sys.exit(1)
        if xlsx_path.suffix.lower() not in (".xlsx", ".xls"):
            print(f"Erro: formato invalido. Use .xlsx")
            sys.exit(1)
    else:
        print("Prestador Mais Proximo")
        print("=" * 40)
        caminho = input("Arraste ou digite o caminho do arquivo XLSX: ").strip()
        caminho = caminho.strip("'\" \n")
        if not caminho:
            print("Nenhum arquivo informado. Encerrando.")
            sys.exit(1)
        xlsx_path = Path(caminho)
        if not xlsx_path.exists():
            print(f"Erro: arquivo nao encontrado: {xlsx_path}")
            sys.exit(1)

    inicio = time.time()
    converter_xlsx(xlsx_path)
    processar()
    duracao = time.time() - inicio

    print(f"\nTempo total: {duracao / 60:.1f} min ({duracao:.0f}s)")
    print("\nPressione Enter para fechar...", end="")
    input()


if __name__ == "__main__":
    main()
