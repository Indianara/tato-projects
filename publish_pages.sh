#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "Preparando arquivos do site..."
./prepare_pages.sh

echo "Publicando no GitHub Pages..."
git add docs/
if git diff --cached --quiet; then
  echo "Nenhuma alteração para publicar."
else
  git commit -m "publicar dashboard $(date '+%Y-%m-%d %H:%M:%S')"
  git push origin main
  echo "Publicado com sucesso!"
fi

echo ""
echo "URL: https://indianaralopess.github.io/tato-projects/"
