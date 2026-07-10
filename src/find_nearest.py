"""
Script principal: encontra os 3 prestadores mais próximos para cada carro.

Uso:
    python src/find_nearest.py

Saída:
    output/prestadores_proximos.csv
"""

import csv
import re
import sys
import time
from pathlib import Path

import pandas as pd
from tqdm import tqdm

# Adiciona o diretório raiz ao path para importar módulos locais
sys.path.insert(0, str(Path(__file__).parent))

from geocoder import batch_geocode, normalize_cep
from distance import find_nearest

# ─── Configurações ───────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
FILES_DIR = BASE_DIR / "Files"
OUTPUT_DIR = BASE_DIR / "output"

AGENDAMENTOS_FILE = FILES_DIR / "pendente_para_instalacao.csv"
PRESTADORES_FILE = FILES_DIR / "Base Prestadores.csv"
OUTPUT_FILE = OUTPUT_DIR / "prestadores_proximos.csv"

TOP_N = 3           # Quantos prestadores no resultado final
PRE_FILTER = 3     # Candidatos a passar para o OSRM após Haversine
OSRM_DELAY = 0.5    # Segundos entre chamadas OSRM

# Regex para extrair CEP do campo Endereço dos agendamentos
# Exemplos: "CEP: 48.009-506" ou "CEP: 48009506"
CEP_REGEX = re.compile(r"CEP[:\s]+([0-9]{2}\.?[0-9]{3}-?[0-9]{3})")


# ─── Parsing ─────────────────────────────────────────────────────────────────

def extract_cep(address: str) -> str:
    """Extrai CEP de um campo de endereço livre."""
    if not isinstance(address, str):
        return ""
    match = CEP_REGEX.search(address)
    return normalize_cep(match.group(1)) if match else ""


def load_agendamentos() -> pd.DataFrame:
    """Carrega e normaliza o CSV de agendamentos."""
    df = pd.read_csv(AGENDAMENTOS_FILE, dtype=str, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()

    df["cep_carro"] = df["Endereço"].apply(extract_cep)

    # Usa colunas já existentes de cidade/estado para fallback de geocoding
    df["_city"] = df.get("Cidade", pd.Series(dtype=str)).fillna("")
    df["_state"] = df.get("Estado", pd.Series(dtype=str)).fillna("")

    print(f"  Pendente para instalação carregados: {len(df)} carros")
    sem_cep = (df["cep_carro"] == "").sum()
    if sem_cep:
        print(f"  ⚠  {sem_cep} carros sem CEP extraído (usarão cidade/estado no fallback)")

    return df


def load_prestadores() -> pd.DataFrame:
    """Carrega e normaliza o CSV de prestadores."""
    df = pd.read_csv(PRESTADORES_FILE, dtype=str, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()

    # Normaliza CEP da coluna dedicada
    df["cep_prestador"] = df["CEP"].apply(
        lambda x: normalize_cep(x) if isinstance(x, str) else ""
    )

    print(f"  Prestadores carregados: {len(df)} registros")
    return df


# ─── Geocodificação ──────────────────────────────────────────────────────────

def build_geocode_entries(df_carros: pd.DataFrame, df_prestadores: pd.DataFrame) -> list[dict]:
    """Monta lista unificada de CEPs para geocodificar em lote."""
    entries = []

    for _, row in df_carros.iterrows():
        if row["cep_carro"]:
            entries.append({
                "cep": row["cep_carro"],
                "city": row["_city"],
                "state": row["_state"],
            })

    for _, row in df_prestadores.iterrows():
        if row["cep_prestador"]:
            entries.append({
                "cep": row["cep_prestador"],
                "city": row.get("Cidade", ""),
                "state": row.get("UF", ""),
            })

    return entries


# ─── Construção dos candidatos ────────────────────────────────────────────────

def build_candidates(df_prestadores: pd.DataFrame, geo: dict) -> list[dict]:
    """
    Converte o DataFrame de prestadores em lista de dicts com coordenadas.
    Um prestador pode ter múltiplos endereços (múltiplas linhas no CSV);
    cada endereço é um candidato independente.
    """
    candidates = []
    for _, row in df_prestadores.iterrows():
        cep = row["cep_prestador"]
        coords = geo.get(cep)
        if not coords:
            continue

        nome_fantasia = row.get("Nome Fantasia", "") or row.get("Nome", "")
        candidates.append({
            "lat": coords["lat"],
            "lng": coords["lng"],
            "nome": nome_fantasia.strip(),
            "endereco": _format_prestador_address(row),
            "cep": cep,
            "cidade": row.get("Cidade", ""),
            "uf": row.get("UF", ""),
            "telefone": row.get("Telefone 1", ""),
        })

    print(f"  Candidatos com coordenadas: {len(candidates)}/{len(df_prestadores)}")
    return candidates


def _format_prestador_address(row: pd.Series) -> str:
    parts = [
        row.get("Endereço", ""),
        row.get("Bairro", ""),
        row.get("Cidade", ""),
        row.get("UF", ""),
        row.get("CEP", ""),
    ]
    return ", ".join(p for p in parts if isinstance(p, str) and p.strip())


# ─── Processamento principal ──────────────────────────────────────────────────

def process(
    df_carros: pd.DataFrame,
    candidates: list[dict],
    geo: dict,
    output_file: Path,
) -> None:
    """
    Para cada carro, encontra os TOP_N prestadores mais próximos.
    Escreve cada resultado direto no CSV (incremental).
    """
    # Define colunas e cria arquivo com headers
    fieldnames = [
        "Placa",
        "Associado",
        "Endereço",
        "Cidade",
        "UF",
        "Modelo",
        "Tipo",
        "Situação",
        "Fone_Associado",
    ]
    for i in range(1, TOP_N + 1):
        fieldnames.extend(
            [
                f"Prestador_{i}_Nome",
                f"Prestador_{i}_Endereco",
                f"Prestador_{i}_Distancia_km",
                f"Prestador_{i}_Telefone",
            ]
        )

    sem_coordenadas = 0

    with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for _, carro in tqdm(
            df_carros.iterrows(), total=len(df_carros), desc="Processando carros"
        ):
            cep = carro["cep_carro"]
            coords = geo.get(cep)

            row = {
                "Placa": carro.get("Placa", ""),
                "Associado": carro.get("Associado", ""),
                "Endereço": carro.get("Endereço", ""),
                "Cidade": carro.get("Cidade", ""),
                "UF": carro.get("UF", ""),
                "Modelo": carro.get("Modelo", ""),
                "Tipo": carro.get("Tipo", ""),
                "Situação": carro.get("Situação Rastreador", ""),
                "Fone_Associado": carro.get("Fone(1)", "") or carro.get("Fone(2)", ""),
            }

            if not coords:
                sem_coordenadas += 1
                for i in range(1, TOP_N + 1):
                    row[f"Prestador_{i}_Nome"] = ""
                    row[f"Prestador_{i}_Endereco"] = ""
                    row[f"Prestador_{i}_Distancia_km"] = ""
                    row[f"Prestador_{i}_Telefone"] = ""
                writer.writerow(row)
                continue

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
                    p = nearest[i - 1]
                    row[f"Prestador_{i}_Nome"] = p.get("nome", "")
                    row[f"Prestador_{i}_Endereco"] = p.get("endereco", "")
                    row[f"Prestador_{i}_Distancia_km"] = p.get("road_km", "")
                    row[f"Prestador_{i}_Telefone"] = p.get("telefone", "")
                else:
                    row[f"Prestador_{i}_Nome"] = ""
                    row[f"Prestador_{i}_Endereco"] = ""
                    row[f"Prestador_{i}_Distancia_km"] = ""
                    row[f"Prestador_{i}_Telefone"] = ""

            writer.writerow(row)
            f.flush()  # Força write no disco a cada linha

    if sem_coordenadas:
        print(
            f"\n  ⚠  {sem_coordenadas} carros sem coordenadas — sem resultado de prestador."
        )


# ─── Entry point ─────────────────────────────────────────────────────────────

def main():
    print("\n=== Prestador Mais Próximo ===\n")
    start = time.time()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Carrega dados
    print("[1/4] Carregando CSVs...")
    df_carros = load_agendamentos()
    df_prestadores = load_prestadores()

    # 2. Geocodifica todos os CEPs únicos
    print("\n[2/4] Geocodificando endereços...")
    entries = build_geocode_entries(df_carros, df_prestadores)
    geo = batch_geocode(entries, verbose=True)

    # 3. Monta lista de candidatos (prestadores com coordenadas)
    print("\n[3/4] Preparando candidatos...")
    candidates = build_candidates(df_prestadores, geo)

    if not candidates:
        print("ERRO: Nenhum prestador geocodificado. Verifique sua conexão e os CEPs.")
        sys.exit(1)

    # 4. Processa cada carro
    print(f"\n[4/4] Calculando {TOP_N} prestadores mais próximos por carro...")
    print(f"      Usando Haversine (top {PRE_FILTER}) → OSRM road distance → top {TOP_N}\n")
    process(df_carros, candidates, geo, OUTPUT_FILE)

    elapsed = time.time() - start
    print(f"\n✓ Concluído em {elapsed:.1f}s")
    print(f"  Resultado salvo em: {OUTPUT_FILE}")
    print(f"  Total de carros processados: {len(df_carros)}")


if __name__ == "__main__":
    main()
