#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

REPO_NAME="${PAGES_REPO_NAME:-verbose-octo-dollop}"
OWNER="${PAGES_REPO_OWNER:-indianaralopess}"
DEFAULT_BRANCH="${PAGES_DEFAULT_BRANCH:-main}"
RUN_PROCESS="${PAGES_RUN_PROCESS:-0}"

GIT_TOKEN="${GITHUB_TOKEN:-${GITHUB_PAT:-}}"

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Comando obrigatório não encontrado: $command_name"
    exit 1
  fi
}

if [[ "$RUN_PROCESS" == "1" ]]; then
  echo "Executando processamento local..."
  .venv/bin/python main2.py
fi

echo "Preparando arquivos do site..."
./prepare_pages.sh

echo "Publicando no GitHub Pages..."
SITE_DIR="docs"
pushd "$SITE_DIR" >/dev/null

git init -b "$DEFAULT_BRANCH" 2>/dev/null || true
git remote remove origin 2>/dev/null || true

# Estratégia de autenticação:
# 1. Se GITHUB_PAT foi passado → usa token na URL
# 2. Senão, tenta gh CLI (já autenticado localmente)
if [[ -n "$GIT_TOKEN" ]]; then
  REMOTE_URL="https://${GIT_TOKEN}@github.com/${OWNER}/${REPO_NAME}.git"
  git remote add origin "$REMOTE_URL"
  echo "  Autenticação: token"
else
  REMOTE_URL="https://github.com/${OWNER}/${REPO_NAME}.git"
  git remote add origin "$REMOTE_URL"
  echo "  Autenticação: credenciais locais / gh"
fi

git add .

if git diff --cached --quiet; then
  echo "Nenhuma alteração para publicar."
else
  git commit -m "Publicar dashboard $(date '+%Y-%m-%d %H:%M:%S')"
  git push -u origin "$DEFAULT_BRANCH" --force
  echo "Publicado com sucesso!"
fi

popd >/dev/null

echo ""
echo "URL: https://$OWNER.github.io/$REPO_NAME/"
