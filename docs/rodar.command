#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

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
HASH=$(git log -1 --format=%h 2>/dev/null || echo "N/A")
DATA=$(git log -1 --format="%ad %H:%M" --date=short 2>/dev/null || echo "N/A")
PUB=$(git log -1 --grep="publicar dashboard" --format="%ad %H:%M" --date=short 2>/dev/null || echo "N/A")
echo "  Versao:     $HASH ($DATA)"
echo "  Publicado:  $PUB"
echo "=============================================="
echo ""

# ── Verificar Python ─────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "ERRO: Python 3 nao encontrado."
    echo "Instale em: https://www.python.org/downloads/"
    read -p "Pressione Enter para fechar..."
    exit 1
fi

# ── Venv + dependencias ──────────────────────────
if [[ ! -d ".venv" ]]; then
    info "Configurando ambiente pela primeira vez..."
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q -r requirements.txt
ok "Dependencias OK"

# ── Selecionar XLSX ──────────────────────────────
echo ""
read -p "Arraste o arquivo XLSX para aqui: " XLSX_PATH
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
URL="https://indianara.github.io/tato-projects/"
echo ""
echo "  Site: $URL"
echo "  Abrindo navegador..."
open "$URL"
echo ""
read -p "Pressione Enter para fechar..."
