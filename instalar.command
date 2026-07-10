#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────
#  Prestador Mais Próximo — Instalador e Executor
#  Baixou esse arquivo? Dê dois cliques!
#  Ele clona o repositório, instala tudo,
#  pergunta qual XLSX usar, processa e publica.
# ─────────────────────────────────────────────────────

REPO_URL="https://github.com/Indianara/tato-projects.git"
REPO_DIR="tato-projects"

VERDE='\033[0;32m'
AZUL='\033[0;34m'
AMARELO='\033[1;33m'
RESET='\033[0m'

info()  { echo -e "${AZUL}[INFO]${RESET} $1"; }
ok()    { echo -e "${VERDE}[OK]${RESET}   $1"; }

clear
echo ""
echo "=============================================="
echo "    Prestador Mais Proximo"
echo "=============================================="
echo ""

# ── Verificar Python ─────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "ERRO: Python 3 nao encontrado."
    echo "Instale em: https://www.python.org/downloads/"
    read -p "Pressione Enter para fechar..."
    exit 1
fi

# ── Verificar git ────────────────────────────────
if ! command -v git &>/dev/null; then
    echo "ERRO: Git nao encontrado."
    echo "Instale em: https://git-scm.com/downloads"
    read -p "Pressione Enter para fechar..."
    exit 1
fi

# ── Clonar / Atualizar repositório ───────────────
info "Baixando o projeto..."

if [[ -d "$REPO_DIR" ]]; then
    cd "$REPO_DIR"
    git fetch origin
    git reset --hard origin/main
    cd ..
else
    git clone "$REPO_URL"
fi

cd "$REPO_DIR"
ok "Projeto baixado"

# ── Venv + dependencias ──────────────────────────
if [[ ! -d ".venv" ]]; then
    info "Configurando ambiente..."
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q -r requirements.txt
ok "Dependencias instaladas"

# ── Selecionar XLSX ──────────────────────────────
echo ""
read -p "Arraste o arquivo XLSX para aqui e pressione Enter: " XLSX_PATH
XLSX_PATH=$(echo "$XLSX_PATH" | sed "s/^['\"]//; s/['\"]$//" | xargs)

if [[ ! -f "$XLSX_PATH" ]]; then
    echo ""
    echo "  ERRO: Arquivo nao encontrado"
    read -p "  Pressione Enter para fechar..."
    exit 1
fi

# ── Converter XLSX → CSV ─────────────────────────
echo ""
info "Convertendo XLSX → CSV..."
python3 -c "
import pandas as pd
df = pd.read_excel('$XLSX_PATH', engine='openpyxl')
df.columns = df.iloc[0]
df = df.iloc[1:].reset_index(drop=True)
df.to_csv('Files/pendente_para_instalacao.csv', index=False, encoding='utf-8-sig')
print(f'  {len(df)} registros convertidos')
"
ok "Arquivo convertido"

# ── Rodar pipeline ───────────────────────────────
echo ""
info "Executando pipeline..."
echo ""
python3 src/main2.py

# ── Fim ──────────────────────────────────────────
echo ""
echo "=============================================="
echo "  PROCESSAMENTO CONCLUIDO!"
echo "=============================================="
echo ""
echo "  Site: https://indianara.github.io/tato-projects/"
echo ""
read -p "Pressione Enter para fechar..."
