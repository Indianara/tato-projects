#!/usr/bin/env python3
"""
Script pontual: lê resultado_final.csv existente e troca
Prestador_i_Nome (fantasia) → Prestador_i_Nome_Legal (razão social)
e cria Prestador_i_Nome_Fantasia com o valor antigo.

Uso:
  python3 src/fix_nome_prestador.py
"""

import csv
from pathlib import Path

OUTPUT_FILE = Path(__file__).parent.parent / "output" / "resultado_final.csv"
TOP_N = 3

with open(OUTPUT_FILE, "r", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames.copy()
    rows = list(reader)

if not fieldnames:
    print("CSV vazio ou inexistente.")
    exit(1)

# Adicionar colunas Nome_Fantasia se não existirem
novas = []
for i in range(1, TOP_N + 1):
    col_fantasia = f"Prestador_{i}_Nome_Fantasia"
    if col_fantasia not in fieldnames:
        fieldnames.insert(fieldnames.index(f"Prestador_{i}_Nome") + 1, col_fantasia)
        novas.append(col_fantasia)

trocas = 0
for row in rows:
    for i in range(1, TOP_N + 1):
        col_nome = f"Prestador_{i}_Nome"
        col_legal = f"Prestador_{i}_Nome_Legal"
        col_fantasia = f"Prestador_{i}_Nome_Fantasia"

        fantasia = row.get(col_nome, "").strip()
        legal = row.get(col_legal, "").strip()

        if legal:
            # Guardar fantasia na nova coluna
            row[col_fantasia] = fantasia
            # Trocar nome para razão social
            row[col_nome] = legal
            trocas += 1

with open(OUTPUT_FILE, "w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)

print(f"✅ {trocas} células atualizadas — fantasia movido para Nome_Fantasia, Nome agora é razão social.")
print(f"   Colunas adicionadas: {', '.join(novas)}")
