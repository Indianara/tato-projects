"""
Módulo de normalização de dados brutos.

Lê os CSVs de entrada e produz CSVs padronizados com:
  - CEP limpo (8 dígitos)
  - UF normalizada (sigla 2 letras)
  - Endereço decomposto em partes (logradouro, numero, complemento,
    bairro, cidade, estado, CEP)
  - Colunas mapeadas para nomes canônicos
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


def _safe_str(val) -> str:
    """Converte valor para string, tratando NaN como vazio."""
    if pd.isna(val):
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s

UF_MAP = {
    "acre": "AC", "alagoas": "AL", "amapa": "AP", "amapá": "AP",
    "amazonas": "AM", "bahia": "BA", "ceara": "CE", "ceará": "CE",
    "distrito federal": "DF", "espirito santo": "ES",
    "espírito santo": "ES", "goias": "GO", "goiás": "GO",
    "maranhao": "MA", "maranhão": "MA", "mato grosso": "MT",
    "mato grosso do sul": "MS", "minas gerais": "MG",
    "para": "PA", "pará": "PA", "paraiba": "PB", "paraíba": "PB",
    "parana": "PR", "paraná": "PR", "pernambuco": "PE",
    "piaui": "PI", "piauí": "PI", "rio de janeiro": "RJ",
    "rio grande do norte": "RN", "rio grande do sul": "RS",
    "rondonia": "RO", "rondônia": "RO", "roraima": "RR",
    "santa catarina": "SC", "sao paulo": "SP", "são paulo": "SP",
    "sergipe": "SE", "tocantins": "TO",
}
UF_SET = set(UF_MAP.values())

CEP_REGEX = re.compile(r"CEP[:\s]+([\d\.\-]+)", re.IGNORECASE)
SIGLA_UF_REGEX = re.compile(r"^[A-Z]{2}$")


_classificacao_cache: dict[str, str] = {}

def classificar_veiculo(modelo: str) -> str:
    """Classifica um veículo como Carro, Moto ou Caminhão baseado no nome do modelo."""
    if not isinstance(modelo, str) or not modelo.strip():
        return ""
    m = modelo.strip().upper()
    if m in _classificacao_cache:
        return _classificacao_cache[m]

    # Caminhões
    if any(m.startswith(p) for p in [
        "MERCEDES-BENZ - L", "MERCEDES-BENZ - LS", "MERCEDES-BENZ - LK",
        "MERCEDES-BENZ - ACTROS", "MERCEDES-BENZ - ATEGO",
        "MERCEDES-BENZ - ATRON", "MERCEDES-BENZ - AXOR",
        "MERCEDES-BENZ - ACCELO", "MERCEDES-BENZ - SPRINTER",
        "MERCEDES-BENZ - 7", "MERCEDES-BENZ - 9",
        "MERCEDES-BENZ - 12", "MERCEDES-BENZ - 13",
        "MERCEDES-BENZ - 14", "MERCEDES-BENZ - 17",
        "MERCEDES-BENZ - 19", "MERCEDES-BENZ - 27",
        "VOLVO - FH", "VOLVO - FM", "VOLVO - VM", "VOLVO - NL",
        "DAF -", "SCANIA -", "IVECO -", "MAN -",
        "FORD - CARGO",
        "KIA MOTORS - BONGO", "SAAB-SCANIA", "RANDON",
    ]):
        _classificacao_cache[m] = "Caminhão"
        return "Caminhão"

    for p in ["VOLKSWAGEN - 8-", "VOLKSWAGEN - 9-", "VOLKSWAGEN - 11-",
              "VOLKSWAGEN - 15-", "VOLKSWAGEN - 17-", "VOLKSWAGEN - 24-",
              "VOLKSWAGEN - 31-", "VOLKSWAGEN - 40-"]:
        if m.startswith(p):
            _classificacao_cache[m] = "Caminhão"
            return "Caminhão"

    if "CAMINHÃO" in m or "CAMINHAO" in m:
        _classificacao_cache[m] = "Caminhão"
        return "Caminhão"

    truck_num = re.compile(
        r"^(MERCEDES-BENZ|FORD|VOLKSWAGEN|BEE|IVECO) - \d+.*(DIESEL|DIES|DIE\.)"
    )
    if truck_num.match(m):
        _classificacao_cache[m] = "Caminhão"
        return "Caminhão"

    if "SPRINTER" in m or ("VITO" in m and "DIESEL" in m):
        _classificacao_cache[m] = "Caminhão"
        return "Caminhão"

    # Motos
    if m.startswith("YAMAHA -") or m.startswith("HAOJUE -") or m.startswith("BAJAJ -"):
        _classificacao_cache[m] = "Moto"
        return "Moto"
    if any(m.startswith(p) for p in [
        "HONDA - CG", "HONDA - NXR", "HONDA - BIZ", "HONDA - CB",
    ]):
        _classificacao_cache[m] = "Moto"
        return "Moto"
    if any(m.startswith(p) for p in [
        "SHINERAY - XY", "SHINERAY - SHI",
    ]):
        _classificacao_cache[m] = "Moto"
        return "Moto"

    _classificacao_cache[m] = "Carro"
    return "Carro"


def normalize_cep(valor: str) -> str:
    """Remove pontuação do CEP, retorna 8 dígitos ou vazio."""
    if not isinstance(valor, str):
        return ""
    return re.sub(r"\D", "", valor)


def normalize_uf(valor: str) -> str:
    """Normaliza UF: sigla de 2 letras ou nome completo → sigla."""
    if not isinstance(valor, str):
        return ""
    v = valor.strip()
    if len(v) == 2 and v.isalpha():
        return v.upper()
    return UF_MAP.get(v.strip().lower(), v)


def _limpar(valor) -> str:
    """Limpa whitespace de um valor, retorna string."""
    if pd.isna(valor):
        return ""
    s = " ".join(str(valor).split()).strip()
    return "" if s.lower() == "nan" else s


def _limpar_df(df: pd.DataFrame, colunas: list[str]) -> pd.DataFrame:
    """Aplica _limpar em múltiplas colunas."""
    for col in colunas:
        if col in df.columns:
            df[col] = df[col].apply(_limpar)
    return df


def parse_endereco(endereco: str) -> dict:
    """Extrai componentes de um endereço brasileiro de veículo.

    Formato padrão (comum nestes CSVs):
        "Rua X, N - Complemento, Bairro, Cidade, UF, CEP: XXXXX-XXX"

    Retorna dict com:
        cep, estado, cidade, bairro,
        logradouro, numero, complemento,
        endereco_completo (reconstruído limpo para geocoding)

    Regras de extração do número (ordem de tentativa):
      1.  NÚMERO - COMPLEMENTO     (padrão: "32 - CASA", "S/N - CASA 09")
      2.  COMPLEMENTO - NÚMERO      (exceção: "C. Saint Tropez - 22")
      3.  SÓ NÚMERO                 ("91", "S/N")
      4.  Nada disso → numero vazio, tudo vai para logradouro
    """
    res = {
        "cep": "", "estado": "", "cidade": "", "bairro": "",
        "logradouro": "", "numero": "", "complemento": "",
        "endereco_completo": "",
    }
    if not isinstance(endereco, str) or not endereco.strip():
        return res

    texto = endereco.strip()

    # 1. Extrair e remover CEP
    m = CEP_REGEX.search(texto)
    if m:
        res["cep"] = re.sub(r"\D", "", m.group(1))
        texto = texto[: m.start()].strip().rstrip(",").strip()

    # 2. Dividir em partes por vírgula
    partes = [p.strip() for p in texto.split(",") if p.strip()]
    if not partes:
        return res

    # 3. Identificar UF (última sigla de 2 letras ou nome completo)
    uf_idx = None
    for i in range(len(partes) - 1, -1, -1):
        p = partes[i].strip().upper()
        if SIGLA_UF_REGEX.match(p) and p in UF_SET:
            res["estado"] = p
            uf_idx = i
            break
        p_lower = partes[i].strip().lower()
        if p_lower in UF_MAP:
            res["estado"] = UF_MAP[p_lower]
            uf_idx = i
            break

    if uf_idx is not None:
        partes.pop(uf_idx)

    if not partes:
        return res

    # 4. Cidade = último fragmento restante
    res["cidade"] = partes.pop()

    # 5. Bairro = penúltimo (se houver)
    if partes:
        res["bairro"] = partes.pop()

    if not partes:
        return res

    # 6. Extrair logradouro, numero, complemento
    logradouro_parts = [partes[0]]
    rest = partes[1:]
    if rest:
        parte_num = rest[0]

        # Padrão 1: NÚMERO - COMPLEMENTO
        # \s+ antes (evita confundir hífen interno como "45-B - ")
        # \s* depois (suporta "147 -" sem espaço final pós-strip)
        num_re = r"^(S/?N|[\d]+[A-Za-zº]?)\s+[-–]\s*(.*)$"
        m = re.match(num_re, parte_num, re.IGNORECASE)
        if m:
            res["numero"] = m.group(1).upper()
            res["complemento"] = m.group(2).strip()
        else:
            # Padrão 2: COMPLEMENTO - NÚMERO (invertido)
            m = re.match(
                r"^(.*?)\s+[-–]\s*(S/?N|[\d]+[A-Za-zº]?)$",
                parte_num, re.IGNORECASE,
            )
            if m:
                res["numero"] = m.group(2).upper()
                res["complemento"] = m.group(1).strip()
            else:
                # Padrão 3: SÓ NÚMERO
                m = re.match(
                    r"^(S/?N|[\d]+[A-Za-zº]?)$",
                    parte_num, re.IGNORECASE,
                )
                if m:
                    res["numero"] = m.group(1).upper()
                else:
                    # Não conseguiu extrair — tudo em logradouro
                    logradouro_parts.extend(rest)
    else:
        # Só tem o logradouro, sem resto
        pass

    res["logradouro"] = ", ".join(logradouro_parts)

    # 7. Montar endereço completo limpo para geocoding
    comp = [res["logradouro"]]
    num = res["numero"]
    compl = res["complemento"]
    if num:
        if compl:
            comp.append(f"{num} - {compl}")
        else:
            comp.append(num)
    comp.extend([res["bairro"], res["cidade"], res["estado"], res["cep"]])
    res["endereco_completo"] = ", ".join(p for p in comp if p)

    return res


COLUNAS_PARSE = [
    "endereco_completo", "logradouro", "numero", "complemento",
    "bairro", "cidade", "estado", "cep",
]


def _aplicar_parse_endereco(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica parse_endereco e adiciona colunas extraídas."""
    parsed = df["endereco"].apply(parse_endereco)
    for chave in COLUNAS_PARSE:
        df[chave] = parsed.apply(lambda d, k=chave: d.get(k, ""))
    return df


def _renomear_e_limpar(
    df: pd.DataFrame, mapa: dict, fonte: str,
) -> pd.DataFrame:
    """Renomeia colunas segundo mapa, limpa valores, adiciona _fonte."""
    cols_existentes = {k: v for k, v in mapa.items() if k in df.columns}
    df = df.rename(columns=cols_existentes).copy()
    colunas_finais = list(cols_existentes.values())
    df = _limpar_df(df, colunas_finais)
    df["_fonte"] = fonte
    return df


# ─── Associados ───────────────────────────────────────────────────────────────

COLUNAS_AGENDAMENTOS = {
    "Placa": "placa",
    "Placa Mercosul": "placa_mercosul",
    "Chassi": "chassi",
    "Associado": "associado",
    "Situação Rastreador": "situacao_rastreador",
    "Operador": "operador",
    "Valor": "valor",
    "Modelo": "modelo",
    "Obrigatório Rastreador": "obrigatorio_rastreador",
    "Endereço": "endereco",
    "UF": "uf",
    "Estado": "estado",
    "Cidade": "cidade",
    "Fone(1)": "fone_1",
    "Fone(2)": "fone_2",
    "Processo": "processo",
    "Prazo situação atual": "prazo_situacao_atual",
    "Base mais proxima - Nome Fantasia": "base_proxima_nome",
    "Base mais proxima - Endereco": "base_proxima_endereco",
    "Base mais proxima - Distancia (km)": "base_proxima_distancia",
    "Tipo": "tipo",
}

COLUNAS_PENDENTE = {
    "ID Solicitação": "id_solicitacao",
    "Placa": "placa",
    "Placa Mercosul": "placa_mercosul",
    "Chassi": "chassi",
    "Instituição": "instituicao",
    "Associado": "associado",
    "Regional": "regional",
    "Consultor": "consultor",
    "Situação": "situacao",
    "Data Situação do Veículo": "data_situacao_veiculo",
    "Dispositivo": "dispositivo",
    "Rastreador": "rastreador",
    "Situação Rastreador": "situacao_rastreador",
    "Operador": "operador",
    "Data Prazo Cadastro": "data_prazo_cadastro",
    "Data Atribuição Operador": "data_atribuicao_operador",
    "Município Inst.": "municipio_inst",
    "Prestador": "prestador_nome",
    "CPF/CNPJ Prestador": "prestador_cpf_cnpj",
    "Responsável Recebimento": "responsavel_recebimento",
    "Tel. Responsável Receb.": "tel_responsavel_receb",
    "Data Instalação": "data_instalacao",
    "Data Retirada Veículo": "data_retirada_veiculo",
    "Site Rastreador": "site_rastreador",
    "Site Login": "site_login",
    "Custos Totais": "custos_totais",
    "Fipe": "fipe",
    "Valor": "valor",
    "Modelo": "modelo",
    "Obrigatório Rastreador": "obrigatorio_rastreador",
    "E-mail": "email",
    "Endereço": "endereco",
    "Fone(1)": "fone_1",
    "Fone(2)": "fone_2",
    "Processo": "processo",
    "Prazo situa\u00e7\u00e3o atual": "prazo_situacao_atual",
    "Tipo": "tipo",
}



def mapear_agendamentos(path: Path) -> pd.DataFrame:
    print(f"  Lendo pendente para instalação: {path.name}")
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()
    df = _renomear_e_limpar(df, COLUNAS_AGENDAMENTOS, "pendente_instalacao")
    df = _aplicar_parse_endereco(df)

    # Preferir colunas separadas para estado e cidade
    if "uf" in df.columns:
        mask_uf = df["uf"].notna() & (df["uf"] != "")
        df.loc[mask_uf, "estado"] = df.loc[mask_uf, "uf"].apply(normalize_uf)
    if "cidade" in df.columns:
        mask_cid = df["cidade"].notna() & (df["cidade"] != "")
        df.loc[mask_cid, "cidade"] = df.loc[mask_cid, "cidade"]

    print(f"    → {len(df)} linhas normalizadas")
    return df


def mapear_pendente(path: Path) -> pd.DataFrame:
    print(f"  Lendo Pendente: {path.name}")
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig", skiprows=1)
    df.columns = df.columns.str.strip()
    df = _renomear_e_limpar(df, COLUNAS_PENDENTE, "Pendente")
    df = _aplicar_parse_endereco(df)
    if "tipo" not in df.columns or df["tipo"].isna().all() or (df["tipo"] == "").all():
        df["tipo"] = df.get("modelo", "").apply(classificar_veiculo)
    print(f"    \u2192 {len(df)} linhas normalizadas")
    return df


def unificar_associados(
    df_agendamentos: pd.DataFrame,
    df_pendente: pd.DataFrame,
) -> pd.DataFrame:
    """Concatena os dois DataFrames preenchendo colunas ausentes com vazio."""
    colunas_originais = list(
        dict.fromkeys(
            list(COLUNAS_AGENDAMENTOS.values())
            + list(COLUNAS_PENDENTE.values())
        )
    )
    todas_colunas = list(dict.fromkeys(colunas_originais + COLUNAS_PARSE + ["_fonte"]))
    df_a = df_agendamentos.reindex(columns=todas_colunas, fill_value="")
    df_p = df_pendente.reindex(columns=todas_colunas, fill_value="")
    df = pd.concat([df_a, df_p], ignore_index=True, sort=False)
    print(f"    → Unificado: {len(df)} associados ({len(df_a)} + {len(df_p)})")
    return df


# ─── Prestadores ──────────────────────────────────────────────────────────────

COLUNAS_PRESTADORES = {
    "Nome": "nome",
    "Nome Fantasia": "nome_fantasia",
    "Tipo fornecedor": "tipo_fornecedor",
    "Tipo documento": "tipo_documento",
    "CPF/CNPJ": "cpf_cnpj",
    "Classificação": "classificacao",
    "Email": "email",
    "Contato": "contato",
    "Telefone 1": "telefone_1",
    "Telefone 2": "telefone_2",
    "Titular": "titular",
    "Tipo de conta": "tipo_conta",
    "Banco": "banco",
    "Agência": "agencia",
    "Conta": "conta",
    "Chave pix": "chave_pix",
    "Últ. alteração dados financeiros": "ult_alteracao_dados_financeiros",
    "Dia de Pagamento": "dia_pagamento",
    "Endereço": "endereco",
    "Bairro": "bairro",
    "Cidade": "cidade",
    "UF": "uf",
    "CEP": "cep",
    "Data Cadastro": "data_cadastro",
    "Tipos de Veículos": "tipos_veiculos",
    "Observação": "observacao",
    "Valor Instalação": "valor_instalacao",
    "Valor Retirada": "valor_retirada",
    "Valor Manutenção": "valor_manutencao",
    "Valor Instalação (Veículo Pesado)": "valor_instalacao_veiculo_pesado",
    "Valor Retirada (Veículo Pesado)": "valor_retirada_veiculo_pesado",
    "Valor Manutenção (Veículo Pesado)": "valor_manutencao_veiculo_pesado",
    "Valor Visita Frustrada": "valor_visita_frustrada",
    "Valor do KM": "valor_km",
    "Abrangência de KM": "abrangencia_km",
    "CPF": "cpf",
    "Horário Rastreador de Seg a Sex": "horario_seg_sex",
    "Horário Rastreador de Sab": "horario_sab",
    "Horário Rastreador de Dom": "horario_dom",
    "Posto fixo e volante": "posto_fixo_volante",
    "Contrato/termo aceite": "contrato_termo_aceite",
    "Data do status contrato/termo": "data_status_contrato_termo",
}

COLUNAS_PREST_RESERVADAS = [
    "endereco_completo", "logradouro", "numero", "complemento",
    "cep_normalizado", "uf_normalizado",
]


def normalizar_prestadores(path: Path, correcoes: dict | None = None) -> pd.DataFrame:
    print(f"  Lendo Prestadores: {path.name}")
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()

    cols_existentes = {k: v for k, v in COLUNAS_PRESTADORES.items() if k in df.columns}
    df = df.rename(columns=cols_existentes).copy()
    colunas_finais = list(cols_existentes.values())
    df = _limpar_df(df, colunas_finais)

    # Normalizar CEP
    df["cep_normalizado"] = df.get("cep", "").apply(normalize_cep)

    # Aplicar correções de CEP (nome → fantasia)
    if correcoes:
        for idx, row in df.iterrows():
            nome = _safe_str(row.get("nome")).upper()
            if nome in correcoes:
                df.at[idx, "cep_normalizado"] = correcoes[nome]
                continue
            fantasia = _safe_str(row.get("nome_fantasia")).upper()
            if fantasia in correcoes:
                df.at[idx, "cep_normalizado"] = correcoes[fantasia]
        print(f"    ✅ Correções aplicadas: {len(correcoes)} CEPs")

    # Normalizar UF
    df["uf_normalizado"] = df.get("uf", "").apply(normalize_uf)

    # Montar endereco_completo a partir das colunas separadas
    if all(c in df.columns for c in ["endereco", "bairro", "cidade", "uf", "cep"]):
        df["endereco_completo"] = df.apply(
            lambda r: ", ".join(
                p for p in [
                    r.get("endereco", ""),
                    r.get("bairro", ""),
                    r.get("cidade", ""),
                    r.get("uf_normalizado", ""),
                    r.get("cep_normalizado", ""),
                ] if isinstance(p, str) and p.strip()
            ),
            axis=1,
        )

    print(f"    → {len(df)} prestadores normalizados")
    return df


# ─── IO ───────────────────────────────────────────────────────────────────────

def salvar_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"  ✅ Salvo: {path.name} ({len(df)} linhas)")
