#!/usr/bin/env python3
"""
Main 2.0 — Pipeline completo: normalização → geocoding → distâncias.

Uso:
  python3 src/main2.py
"""

import csv
import json
import re
import sys
from pathlib import Path

import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.geocoder import batch_geocode
from src.distance import find_nearest
from src.normalizacao import (
    COLUNAS_AGENDAMENTOS,
    COLUNAS_PENDENTE,
    COLUNAS_PARSE,
    _safe_str,
    mapear_agendamentos,
    mapear_pendente,
    unificar_associados,
    normalizar_prestadores,
    salvar_csv,
)

BASE_DIR = Path(__file__).parent.parent
FILES_DIR = BASE_DIR / "Files"
CACHE_DIR = BASE_DIR / "cache"
OUTPUT_DIR = BASE_DIR / "output"

AGENDAMENTOS_FILE = FILES_DIR / "pendente_para_instalacao.csv"
PENDENTE_FILE = FILES_DIR / "Pendente Instalação - Cartruck.csv"
PRESTADORES_FILE = FILES_DIR / "Base Prestadores.csv"
CEP_CORRECOES_FILE = FILES_DIR / "CEPs_Corrigidos.csv"

OUTPUT_ASSOCIADOS = OUTPUT_DIR / "associados_normalizados.csv"
OUTPUT_PRESTADORES = OUTPUT_DIR / "prestadores_normalizados.csv"
OUTPUT_FINAL = OUTPUT_DIR / "resultado_final.csv"
OUTPUT_SEM_COORD = OUTPUT_DIR / "associados_sem_coordenada.csv"
OUTPUT_PREST_SEM_COORD = OUTPUT_DIR / "prestadores_sem_coordenada.csv"

GEO_CACHE_FILE = CACHE_DIR / "geocode_cache.json"
TOP_N = 3
PRE_FILTER = 3
OSRM_DELAY = 0.5


# ─── Helpers de saída ─────────────────────────────────────────────────────────

def build_fieldnames(vehicle_columns: list[str]) -> list[str]:
    fieldnames = list(vehicle_columns)
    for i in range(1, TOP_N + 1):
        fieldnames += [
            f"Prestador_{i}_Nome", f"Prestador_{i}_Nome_Legal",
            f"Prestador_{i}_CNPJ_CPF", f"Prestador_{i}_Tipo_Fornecedor",
            f"Prestador_{i}_Classificacao", f"Prestador_{i}_Endereco",
            f"Prestador_{i}_Cidade", f"Prestador_{i}_UF",
            f"Prestador_{i}_CEP", f"Prestador_{i}_Distancia_km",
            f"Prestador_{i}_Contato", f"Prestador_{i}_Telefone",
            f"Prestador_{i}_Telefone_2", f"Prestador_{i}_Email",
            f"Prestador_{i}_Tipos_Veiculos", f"Prestador_{i}_Observacao",
        ]
    return fieldnames


def fill_prestador_row(row: dict, i: int, p: dict) -> None:
    for k, v in [
        ("Nome", "nome"), ("Nome_Legal", "nome_legal"),
        ("CNPJ_CPF", "cnpj_cpf"), ("Tipo_Fornecedor", "tipo_fornecedor"),
        ("Classificacao", "classificacao"), ("Endereco", "endereco"),
        ("Cidade", "cidade"), ("UF", "uf"),
        ("CEP", "cep"), ("Distancia_km", "road_km"),
        ("Contato", "contato"), ("Telefone", "telefone"),
        ("Telefone_2", "telefone_2"), ("Email", "email"),
        ("Tipos_Veiculos", "tipos_veiculos"), ("Observacao", "observacao"),
    ]:
        row[f"Prestador_{i}_{k}"] = p.get(v, "")


def clear_prestador_row(row: dict, i: int) -> None:
    sufixos = [
        "Nome", "Nome_Legal", "CNPJ_CPF", "Tipo_Fornecedor", "Classificacao",
        "Endereco", "Cidade", "UF", "CEP", "Distancia_km",
        "Contato", "Telefone", "Telefone_2", "Email", "Tipos_Veiculos", "Observacao",
    ]
    for s in sufixos:
        row[f"Prestador_{i}_{s}"] = ""


# ─── Build candidates (colunas normalizadas) ──────────────────────────────────

def build_candidates(df_prest: pd.DataFrame, geo: dict, coord_manuais: dict | None = None) -> list[dict]:
    candidates = []
    for _, row in df_prest.iterrows():
        cep = _safe_str(row.get("cep_normalizado"))
        nome_legal = _safe_str(row.get("nome"))
        nome_fantasia = _safe_str(row.get("nome_fantasia"))

        # Coordenada manual (nome → lat, lon) tem prioridade
        lat = None
        lng = None
        if coord_manuais:
            chave = nome_legal.upper()
            manual = coord_manuais.get(chave)
            if not manual:
                chave = nome_fantasia.upper()
                manual = coord_manuais.get(chave)
            if manual:
                lat, lng = manual

        # Fallback para cache do geocoding
        if lat is None:
            coords = geo.get(cep)
            if coords:
                lat = coords["lat"]
                lng = coords["lng"]

        if lat is None:
            continue

        candidates.append({
            "lat": lat,
            "lng": lng,
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
    print(f"  Candidatos com coordenadas: {len(candidates)}/{len(df_prest)}")
    return candidates


# ─── Process (reaproveita lógica do main.py) ──────────────────────────────────

def process(df_com_coord: pd.DataFrame, candidates: list[dict], geo: dict) -> None:
    vehicle_columns = [c for c in df_com_coord.columns if not c.startswith("_")]
    fieldnames = build_fieldnames(vehicle_columns)

    ceps_unicos = df_com_coord["cep"].dropna().unique()
    print(f"  {len(ceps_unicos)} CEPs únicos a calcular via OSRM")

    with open(OUTPUT_FINAL, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        for _, carro in tqdm(df_com_coord.iterrows(), total=len(df_com_coord), desc="  Processando"):
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


def carregar_correcoes_cep(path: Path) -> tuple[dict, dict]:
    """Retorna (dict cep_correcoes, dict coord_manuais).
    
    cep_correcoes: {nome_upper: cep_correto_normalizado}
    coord_manuais: {nome_upper: (lat, lon)}
    """
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
        cep = re.sub(r"\D", "", _safe_str(row.get("Cep_Correto")))
        if len(cep) == 8:
            correcoes[nome] = cep
    if coords:
        print(f"  📍 {len(coords)} coordenadas manuais carregadas")
    if correcoes:
        print(f"  📋 {len(correcoes)} correções de CEP carregadas")
    return correcoes, coords


def _df_vazio_agendamentos() -> pd.DataFrame:
    cols = list(COLUNAS_AGENDAMENTOS.values())
    cols = list(dict.fromkeys(cols + COLUNAS_PARSE + ["_fonte"]))
    return pd.DataFrame(columns=cols)


def _df_vazio_pendente() -> pd.DataFrame:
    cols = list(COLUNAS_PENDENTE.values())
    cols = list(dict.fromkeys(cols + COLUNAS_PARSE + ["_fonte"]))
    return pd.DataFrame(columns=cols)


# ─── Main ─────────────────────────────────────────────────────────────────────

def carregar_ou_normalizar() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Normaliza os CSVs brutos sempre (sobrescreve os existentes)."""

    print("\n  [1/4] Normalizando pendente para instalação...")
    if AGENDAMENTOS_FILE.exists():
        # Detecta se é formato Pendente (linha "Fila de Rastreadores")
        first = pd.read_csv(AGENDAMENTOS_FILE, nrows=0, encoding="utf-8-sig")
        if "Fila" in str(first.columns[0]):
            print(f"  Formato Pendente detectado em {AGENDAMENTOS_FILE.name}, lendo com skiprows=1...")
            df_agend = mapear_pendente(AGENDAMENTOS_FILE)
        else:
            df_agend = mapear_agendamentos(AGENDAMENTOS_FILE)
    else:
        print(f"  ⚠ Arquivo não encontrado: {AGENDAMENTOS_FILE.name}, pulando...")
        df_agend = _df_vazio_agendamentos()

    print("\n  [2/4] Normalizando Pendente...")
    if PENDENTE_FILE.exists():
        df_pend = mapear_pendente(PENDENTE_FILE)
    else:
        print(f"  ⚠ Arquivo não encontrado: {PENDENTE_FILE.name}, pulando...")
        df_pend = _df_vazio_pendente()

    if df_agend.empty and df_pend.empty:
        print("  ❌ Nenhum arquivo de entrada encontrado. Abortando.")
        sys.exit(1)

    print("\n  [3/4] Unificando associados...")
    df_a = unificar_associados(df_agend, df_pend)
    salvar_csv(df_a, OUTPUT_ASSOCIADOS)

    print("\n  [4/4] Normalizando prestadores...")
    correcoes, coord_manuais = carregar_correcoes_cep(CEP_CORRECOES_FILE)
    df_p = normalizar_prestadores(PRESTADORES_FILE, correcoes)
    salvar_csv(df_p, OUTPUT_PRESTADORES)

    return df_a, df_p, coord_manuais


def main():
    print("=" * 60)
    print("  Prestador Mais Próximo — Pipeline 2.0")
    print("=" * 60)

    # ── 1. Normalização ──────────────────────────────────────────────────
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("\n[1/6] Carregando/normalizando dados...")
    df_assoc, df_prest, coord_manuais = carregar_ou_normalizar()

    # ── 2. Geocoding ─────────────────────────────────────────────────────
    print("\n[2/6] Coletando CEPs únicos para geocodificar...")
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
        print(f"  {unicos} CEPs únicos novos para geocodificar...")
        batch_geocode(entries, verbose=True)
        with open(GEO_CACHE_FILE, "r", encoding="utf-8") as f:
            geo = json.load(f)
        print(f"  Cache atualizado: {len(geo)} CEPs total")
    else:
        print("  Todos os CEPs já estão no cache ✓")

    # ── 3. Separar veículos com/sem coordenada ────────────────────────────
    print("\n[3/6] Separando veículos...")
    def has_coords(cep):
        return bool(cep) and bool(geo.get(cep))

    df_assoc["cep"] = df_assoc["cep"].fillna("")
    df_com = df_assoc[df_assoc["cep"].map(has_coords)].copy()
    df_sem = df_assoc[~df_assoc["cep"].map(has_coords)].copy()
    print(f"  Com coordenada: {len(df_com)} veículos")
    print(f"  Sem coordenada: {len(df_sem)} veículos → {OUTPUT_SEM_COORD.name}")

    if not df_sem.empty:
        salvar_csv(df_sem, OUTPUT_SEM_COORD)

    if df_com.empty:
        print("\n⚠  Nenhum veículo com coordenada. Encerrando.")
        return

    # ── 4. Prestadores sem coordenada ─────────────────────────────────────
    print("\n[4/6] Prestadores sem coordenada...")
    mask = ~df_prest["cep_normalizado"].fillna("").map(has_coords)
    df_prest_sem = df_prest[mask].copy()
    if not df_prest_sem.empty:
        salvar_csv(df_prest_sem, OUTPUT_PREST_SEM_COORD)
        print(f"  {len(df_prest_sem)} prestadores → {OUTPUT_PREST_SEM_COORD.name}")
    else:
        print("  Todos os prestadores têm coordenada ✓")

    # ── 5. Build candidates ───────────────────────────────────────────────
    print("\n[5/6] Construindo lista de candidatos...")
    candidates = build_candidates(df_prest, geo, coord_manuais)
    if not candidates:
        print("\n⚠  Nenhum prestador com coordenada. Encerrando.")
        return

    # ── 6. Processar (distâncias + resultado final) ───────────────────────
    print("\n[6/6] Calculando distâncias e gerando resultado final...")
    process(df_com, candidates, geo)

    # ── 7. Publicar site ──────────────────────────────────────────────────
    print("\n[7/7] Publicando site no GitHub Pages...")
    import subprocess
    subprocess.run(["chmod", "+x", "publish_pages.sh", "prepare_pages.sh"], cwd=BASE_DIR)
    subprocess.run(["./publish_pages.sh"], cwd=BASE_DIR)

    # ── Fim ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  ✅ Pipeline 2.0 concluída!")
    print(f"     {len(df_com)} veículos processados → {OUTPUT_FINAL.name}")
    print(f"     {len(df_sem)} veículos sem coord  → {OUTPUT_SEM_COORD.name}")
    print(f"     {len(df_prest_sem)} prestadores sem coord → {OUTPUT_PREST_SEM_COORD.name}")
    print("=" * 60)


if __name__ == "__main__":
    main()
