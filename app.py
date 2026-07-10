import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from src.geocoder import batch_geocode
from src.distance import find_nearest, top_n_haversine
from src.normalizacao import (
    _safe_str,
    mapear_pendente,
    normalizar_prestadores,
    unificar_associados,
    salvar_csv,
)

BASE_DIR = Path(__file__).parent
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


def process_vehicles(df_com, candidates, geo, use_osrm):
    vehicle_columns = [c for c in df_com.columns if not c.startswith("_")]
    fieldnames = build_fieldnames(vehicle_columns)
    results = []

    progress_bar = st.progress(0, text="Calculando distâncias...")

    for idx, (_, carro) in enumerate(df_com.iterrows()):
        cep = str(carro.get("cep", "") or "")
        row = {col: _safe_str(carro.get(col)) for col in vehicle_columns}
        nearest = []

        coords = geo.get(cep)
        if coords:
            if use_osrm:
                nearest = find_nearest(
                    origin_lat=coords["lat"],
                    origin_lng=coords["lng"],
                    candidates=candidates,
                    top_n=TOP_N,
                    pre_filter=PRE_FILTER,
                    osrm_delay=OSRM_DELAY,
                )
            else:
                haversine_results = top_n_haversine(
                    coords["lat"], coords["lng"], candidates, n=PRE_FILTER
                )
                for h in haversine_results[:TOP_N]:
                    nearest.append({**h, "road_km": h.get("haversine_km")})

        for i in range(1, TOP_N + 1):
            if i <= len(nearest):
                fill_prestador_row(row, i, nearest[i - 1])
            else:
                clear_prestador_row(row, i)
        results.append(row)

        progress_bar.progress(
            (idx + 1) / len(df_com),
            text=f"Processando veículo {idx + 1}/{len(df_com)}",
        )

    progress_bar.empty()
    return results, fieldnames


def publish_to_github(token, owner, repo):
    token = token or os.getenv("GITHUB_PAT") or ""

    if not token:
        st.error("GITHUB_PAT não configurado. Crie o arquivo .env ou configure os secrets.")
        return False

    st.info("Preparando arquivos para publicação...")
    prepare = subprocess.run(
        ["./prepare_pages.sh"], capture_output=True, text=True, cwd=BASE_DIR
    )
    if prepare.returncode != 0:
        st.error(f"prepare_pages.sh falhou:\n{prepare.stderr}")
        return False
    st.code(prepare.stdout)

    st.info("Publicando no GitHub Pages...")
    target_url = f"https://{token}@github.com/{owner}/{repo}.git"
    docs_dir = BASE_DIR / "docs"

    try:
        subprocess.run(
            ["git", "init"], capture_output=True, cwd=docs_dir, check=True
        )
        subprocess.run(
            ["git", "checkout", "-b", "main"],
            capture_output=True, cwd=docs_dir, check=True,
        )
        subprocess.run(
            ["git", "add", "."], capture_output=True, cwd=docs_dir, check=True
        )
        subprocess.run(
            ["git", "commit", "-m", f"Publicar dashboard {time.strftime('%Y-%m-%d %H:%M:%S')}"],
            capture_output=True, cwd=docs_dir, check=True,
        )
        subprocess.run(
            ["git", "remote", "remove", "origin"],
            capture_output=True, cwd=docs_dir,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", target_url],
            capture_output=True, cwd=docs_dir, check=True,
        )
        result = subprocess.run(
            ["git", "push", "-u", "origin", "main", "--force"],
            capture_output=True, text=True, cwd=docs_dir,
        )
        if result.returncode != 0:
            st.error(f"Push falhou:\n{result.stderr}")
            return False
        st.code(result.stdout)

        pages_url = f"https://{owner}.github.io/{repo}/"
        st.success(f"Publicado com sucesso! URL: {pages_url}")
        return True
    except subprocess.CalledProcessError as e:
        st.error(f"Erro no git: {e}")
        return False


st.set_page_config(
    page_title="Prestador Mais Próximo",
    page_icon="📍",
    layout="wide",
)

st.title("📍 Prestador Mais Próximo")
st.markdown("Faça upload do arquivo XLSX da fila de rastreadores para processar.")

if not PRESTADORES_FILE.exists():
    st.error(f"Arquivo Base Prestadores.csv não encontrado em {PRESTADORES_FILE}")
    st.stop()

with st.sidebar:
    st.header("Configuração")
    use_osrm = st.checkbox("Usar OSRM (distância por estrada)", value=False)
    if use_osrm:
        st.caption(
            "⚠ OSRM é mais preciso mas muito mais lento "
            "(~0.5s por veículo). Prefira Haversine para processamento rápido."
        )

    st.divider()
    st.header("Publicar no GitHub")
    with st.expander("Configurar publicação"):
        pat_input = st.text_input("GitHub PAT", type="password",
                                  help="Fine-grained token com acesso ao repo de Pages")
        repo_owner = st.text_input("Dono do repositório", value="Indianara")
        repo_name = st.text_input("Nome do repositório", value="tato-projects")

    publish_btn = st.button("📤 Publicar no GitHub Pages", disabled=not pat_input)

uploaded_file = st.file_uploader(
    "Escolha o arquivo XLSX da fila de rastreadores",
    type=["xlsx"],
)

if uploaded_file:
    with st.status("Processando...", expanded=True) as status:
        st.write("💾 Salvando arquivo...")
        xlsx_path = FILES_DIR / "upload_temp.xlsx"
        with open(xlsx_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        st.write("🔄 Convertendo XLSX para CSV...")
        df_xlsx = pd.read_excel(xlsx_path, engine="openpyxl")
        df_xlsx.columns = df_xlsx.iloc[0]
        df_xlsx = df_xlsx.iloc[1:].reset_index(drop=True)
        df_xlsx.to_csv(AGENDAMENTOS_FILE, index=False, encoding="utf-8-sig")
        xlsx_path.unlink()
        st.write(f"✅ Convertido: {len(df_xlsx)} registros")

        st.write("📂 Normalizando dados...")
        df_agend = mapear_pendente(AGENDAMENTOS_FILE)
        df_pend = pd.DataFrame()
        df_a = unificar_associados(df_agend, df_pend)
        salvar_csv(df_a, OUTPUT_ASSOCIADOS)
        st.write(f"✅ Associados normalizados: {len(df_a)}")

        st.write("🏢 Normalizando prestadores...")
        correcoes, coord_manuais = carregar_correcoes_cep(CEP_CORRECOES_FILE)
        df_p = normalizar_prestadores(PRESTADORES_FILE, correcoes)
        salvar_csv(df_p, OUTPUT_PRESTADORES)
        st.write(f"✅ Prestadores normalizados: {len(df_p)}")

        st.write("🌍 Geocodificando endereços...")
        if GEO_CACHE_FILE.exists():
            with open(GEO_CACHE_FILE, "r", encoding="utf-8") as f:
                geo = json.load(f)
        else:
            geo = {}

        entries = []
        for _, row in df_a.iterrows():
            cep = _safe_str(row.get("cep"))
            if cep and not geo.get(cep):
                entries.append({
                    "cep": cep,
                    "city": _safe_str(row.get("cidade")),
                    "state": _safe_str(row.get("estado")),
                    "endereco": _safe_str(row.get("endereco_completo")),
                    "bairro": _safe_str(row.get("bairro")),
                })
        for _, row in df_p.iterrows():
            cep = _safe_str(row.get("cep_normalizado"))
            if cep and not geo.get(cep):
                entries.append({
                    "cep": cep,
                    "city": _safe_str(row.get("cidade")),
                    "state": _safe_str(row.get("uf_normalizado")),
                    "endereco": _safe_str(row.get("endereco_completo")),
                    "bairro": _safe_str(row.get("bairro")),
                })

        if entries:
            geo_progress = st.progress(0, text="Geocodificando CEPs...")
            batch_geocode(entries, verbose=False)
            with open(GEO_CACHE_FILE, "r", encoding="utf-8") as f:
                geo = json.load(f)
            geo_progress.empty()
        st.write(f"✅ Geocode concluído: {len(geo)} CEPs em cache")

        st.write("🔍 Separando veículos com coordenada...")
        df_a["cep"] = df_a["cep"].fillna("")
        df_com = df_a[df_a["cep"].map(lambda c: bool(c) and bool(geo.get(c)))].copy()
        df_sem = df_a[~df_a["cep"].map(lambda c: bool(c) and bool(geo.get(c)))].copy()

        if not df_sem.empty:
            salvar_csv(df_sem, OUTPUT_SEM_COORD)

        if df_com.empty:
            st.error("Nenhum veículo com coordenada encontrado.")
            status.update(label="❌ Processamento falhou", state="error")
            st.stop()

        st.write("📋 Construindo candidatos...")
        candidates = build_candidates(df_p, geo, coord_manuais)
        st.write(f"✅ {len(candidates)} prestadores com coordenada")

        if not candidates:
            st.error("Nenhum prestador com coordenada disponível.")
            status.update(label="❌ Processamento falhou", state="error")
            st.stop()

        st.write(f"{'🛣️' if use_osrm else '📏'} Calculando distâncias...")
        results, fieldnames = process_vehicles(df_com, candidates, geo, use_osrm)

        df_result = pd.DataFrame(results)
        df_result.to_csv(OUTPUT_FINAL, index=False, encoding="utf-8-sig")

        method = "OSRM" if use_osrm else "Haversine"
        st.write(f"✅ {len(results)} veículos processados via {method}")
        status.update(label="✅ Processamento concluído!", state="complete")

    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📊 Resumo")
        st.metric("Veículos processados", len(results))
        st.metric("Sem coordenada", len(df_sem))
        st.metric("Prestadores disponíveis", len(candidates))

    with col2:
        st.subheader("📥 Download")
        if not df_result.empty:
            csv_bytes = df_result.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button(
                label="⬇ Baixar resultado_final.csv",
                data=csv_bytes,
                file_name="resultado_final.csv",
                mime="text/csv",
                use_container_width=True,
            )
        if not df_sem.empty:
            sem_bytes = df_sem.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button(
                label="⬇ Baixar sem_coordenada.csv",
                data=sem_bytes,
                file_name="sem_coordenada.csv",
                mime="text/csv",
                use_container_width=True,
            )

    st.subheader("👁️ Preview")
    st.dataframe(df_result.head(100), use_container_width=True)

if publish_btn:
    with st.spinner("Publicando no GitHub Pages..."):
        success = publish_to_github(pat_input, repo_owner, repo_name)
        if success:
            st.balloons()
