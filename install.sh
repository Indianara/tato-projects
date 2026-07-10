#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────
#  Prestador Mais Próximo — Instalador e Executor
#  Uso:
#    curl -fsSL https://raw.githubusercontent.com/Indianara/tato-projects/main/install.sh | bash
#    ./install.sh /caminho/para/planilha.xlsx
# ─────────────────────────────────────────────────────

REPO_URL="https://github.com/Indianara/tato-projects.git"
REPO_DIR="tato-projects"

VERDE='\033[0;32m'
AZUL='\033[0;34m'
AMARELO='\033[1;33m'
RESET='\033[0m'

info()  { echo -e "${AZUL}[INFO]${RESET} $1"; }
ok()    { echo -e "${VERDE}[OK]${RESET}   $1"; }
aviso() { echo -e "${AMARELO}[AVISO]${RESET} $1"; }

# ── Detectar arquivo XLSX ────────────────────────────
XLSX_PATH=""
for arg in "$@"; do
    if [[ "$arg" != -* && "$arg" != "" ]]; then
        XLSX_PATH="$arg"
        break
    fi
done

if [[ -z "$XLSX_PATH" ]]; then
    echo ""
    echo "  Prestador Mais Próximo"
    echo "  ======================"
    echo ""
    echo "  Uso: ./install.sh /caminho/para/planilha.xlsx"
    echo ""
    echo "  Ou com curl:"
    echo "    curl -fsSL https://raw.githubusercontent.com/Indianara/tato-projects/main/install.sh | bash -s -- /caminho/para/planilha.xlsx"
    echo ""
    read -p "  Arraste ou digite o caminho do arquivo XLSX: " XLSX_PATH
    XLSX_PATH=$(echo "$XLSX_PATH" | sed "s/^['\"]//; s/['\"]$//" | xargs)
fi

if [[ ! -f "$XLSX_PATH" ]]; then
    echo ""
    echo "  ERRO: Arquivo nao encontrado: $XLSX_PATH"
    echo ""
    read -p "  Pressione Enter para fechar..."
    exit 1
fi

echo ""
echo "=============================================="
echo "  Prestador Mais Proximo"
echo "=============================================="
echo ""

# ── 1. Clonar / Atualizar repositório ───────────────
info "Preparando repositorio..."

if [[ -d "$REPO_DIR" ]]; then
    info "Atualizando repositorio existente..."
    cd "$REPO_DIR"
    git fetch origin
    git reset --hard origin/main
    cd ..
else
    info "Clonando repositorio..."
    git clone "$REPO_URL"
fi

cd "$REPO_DIR"
ok "Repositorio pronto em $(pwd)"

# ── 2. Criar venv e instalar dependências ────────────
info "Configurando ambiente Python..."

if [[ ! -d ".venv" ]]; then
    python3 -m venv .venv
    ok "Virtualenv criada"
else
    ok "Virtualenv ja existe"
fi

source .venv/bin/activate
pip install -q -r requirements.txt
ok "Dependencias instaladas"

# ── 3. Converter XLSX para CSV ───────────────────────
info "Convertendo XLSX → CSV..."
python3 -c "
import pandas as pd
df = pd.read_excel('$XLSX_PATH', engine='openpyxl')
df.columns = df.iloc[0]
df = df.iloc[1:].reset_index(drop=True)
df.to_csv('Files/pendente_para_instalacao.csv', index=False, encoding='utf-8-sig')
print(f'{len(df)} registros convertidos')
"
ok "Arquivo convertido: Files/pendente_para_instalacao.csv"

# ── 4. Rodar pipeline (inclui publicação) ────────────
echo ""
info "Executando pipeline..."
echo ""

python3 src/main2.py

# ── 5. Fim ───────────────────────────────────────────
echo ""
echo "=============================================="
echo "  PROCESSAMENTO CONCLUIDO!"
echo "=============================================="
echo "  Resultado: $(pwd)/output/resultado_final.csv"
echo ""

read -p "  Pressione Enter para fechar..."
