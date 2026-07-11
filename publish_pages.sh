#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "Preparando arquivos do site..."
./prepare_pages.sh

# Garante config git para o commit funcionar mesmo sem config global
git config user.name >/dev/null 2>&1 || git config user.name "Prestador Mais Proximo"
git config user.email >/dev/null 2>&1 || git config user.email "prestador@maisproximo.app"

echo "Publicando no GitHub Pages..."
git add docs/
if git diff --cached --quiet; then
  echo "Nenhuma alteração para publicar."
else
  git commit -m "publicar dashboard $(date '+%Y-%m-%d %H:%M:%S')"
  git push origin main
  echo "Publicado com sucesso!"
fi

URL="https://indianara.github.io/tato-projects/"
echo ""
echo "URL: $URL"
echo "Abrindo site no navegador..."
open "$URL"
