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
if cd "$REPO_DIR" 2>/dev/null; then
  HASH=$(git log -1 --format=%h 2>/dev/null || echo "N/A")
  DATA=$(git log -1 --format="%ad %H:%M" --date=short 2>/dev/null || echo "N/A")
  PUB=$(git log -1 --grep="publicar dashboard" --format="%ad %H:%M" --date=short 2>/dev/null || echo "N/A")
  echo "  Versao:     $HASH ($DATA)"
  echo "  Publicado:  $PUB"
  cd ..
fi
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

# ── Garantir autenticação GitHub ──────────────────
ensure_github_auth() {
    if git ls-remote "$REPO_URL" &>/dev/null; then
        return 0
    fi

    echo ""
    echo "=============================================="
    echo "  ACESSO NEGADO AO REPOSITORIO (403)"
    echo "=============================================="
    echo ""
    echo "Este repositorio e privado e requer login no GitHub."
    echo ""

    if command -v gh &>/dev/null; then
        if gh auth status &>/dev/null; then
            ok "GitHub ja autenticado"
            return 0
        fi
    else
        echo "Instalando GitHub CLI..."
        if command -v brew &>/dev/null; then
            brew install gh 2>/dev/null || true
        fi

        if ! command -v gh &>/dev/null; then
            GH_VERSION=$(curl -sL "https://api.github.com/repos/cli/cli/releases/latest" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tag_name'].lstrip('v'))" 2>/dev/null || echo "2.55.0")
            ARCH=$(uname -m)
            if [[ "$ARCH" == "arm64" ]]; then
                GH_URL="https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_macOS_arm64.pkg"
            else
                GH_URL="https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_macOS_amd64.pkg"
            fi

            echo "  Baixando $GH_URL ..."
            curl -sL -o /tmp/gh.pkg "$GH_URL" || {
                echo ""
                echo "  ERRO: Falha ao baixar. Verifique sua internet."
                read -p "  Pressione Enter para fechar..."
                exit 1
            }
            echo "  Instalando (pode solicitar sua senha)..."
            sudo installer -pkg /tmp/gh.pkg -target / 2>/dev/null || true
        fi
    fi

    if ! command -v gh &>/dev/null; then
        echo ""
        echo "  ERRO: Nao foi possivel instalar o GitHub CLI."
        echo "  Instale manualmente em: https://cli.github.com/"
        read -p "  Pressione Enter apos instalar..."
        exit 1
    fi

    echo ""
    echo "Abrindo navegador para login no GitHub..."
    echo "Siga as instrucoes no navegador e depois volte aqui."
    echo ""
    gh auth login --web || {
        echo ""
        echo "  ERRO: Login nao realizado."
        read -p "  Pressione Enter para fechar..."
        exit 1
    }
    echo ""
    ok "Login GitHub realizado com sucesso!"
}

# ── Clonar / Atualizar repositório ───────────────
info "Verificando acesso ao GitHub..."
ensure_github_auth

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
URL="https://indianara.github.io/tato-projects/"
echo ""
echo "  Site: $URL"
echo "  Abrindo navegador..."
open "$URL"
echo ""
read -p "Pressione Enter para fechar..."
