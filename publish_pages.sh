#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

REPO_NAME="${PAGES_REPO_NAME:-tato-projects}"
OWNER="${PAGES_REPO_OWNER:-Indianara}"
DEFAULT_BRANCH="${PAGES_DEFAULT_BRANCH:-main}"
RUN_PROCESS="${PAGES_RUN_PROCESS:-0}"

# Aceita GITHUB_TOKEN ou GITHUB_PAT como env var
GIT_TOKEN="${GITHUB_TOKEN:-${GITHUB_PAT:-}}"

if [[ -z "$GIT_TOKEN" ]]; then
  echo "Erro: GITHUB_PAT ou GITHUB_TOKEN não definido."
  echo "Crie um fine-grained PAT em:"
  echo "  https://github.com/settings/tokens?type=beta"
  echo "Com escopo: Contents: Read and write no repositório $OWNER/$REPO_NAME"
  echo ""
  echo "E defina a variável:"
  echo "  export GITHUB_PAT=github_pat_..."
  exit 1
fi

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Comando obrigatório não encontrado: $command_name"
    exit 1
  fi
}

remote_url() {
  echo "https://${GIT_TOKEN}@github.com/${OWNER}/${REPO_NAME}.git"
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
git remote add origin "$(remote_url)"
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
