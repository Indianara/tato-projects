#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

SITE_DIR="docs"
OUTPUT_DIR="output"

mkdir -p "$SITE_DIR/output"

cp dashboard.html "$SITE_DIR/index.html"
touch "$SITE_DIR/.nojekyll"

rm -f "$SITE_DIR/output/resultado_final.parcial.csv"
rm -f "$SITE_DIR/output/resultado_final.csv"
rm -f "$SITE_DIR/output/sem_coordenada.csv"

copied_files=0

for file_name in resultado_final.parcial.csv resultado_final.csv sem_coordenada.csv; do
  source_file="$OUTPUT_DIR/$file_name"
  if [[ -f "$source_file" ]]; then
    cp "$source_file" "$SITE_DIR/output/$file_name"
    copied_files=$((copied_files + 1))
  fi
done

if [[ "$copied_files" -eq 0 ]]; then
  echo "Nenhum CSV encontrado em $OUTPUT_DIR/. Execute o processamento antes de preparar o site."
  exit 1
fi

echo "Site estático preparado em $SITE_DIR/."
echo "Arquivo principal: $SITE_DIR/index.html"
echo "Arquivos de dados copiados: $copied_files"