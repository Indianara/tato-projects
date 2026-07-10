# Prestador Mais Próximo

Prestador Mais Próximo is a local Python data pipeline plus a static HTML dashboard used to match each vehicle or service row to the nearest service providers and publish the result as a static website.

The repository has two responsibilities:

1. Process source CSV files locally and generate enriched result CSVs.
2. Expose those CSVs through a static dashboard that can run locally or on GitHub Pages.

This README is intended to be the authoritative English reference for developers, operators, and agents. It documents the current code behavior, business rules, runtime assumptions, outputs, dashboard rules, and publication flow.

## What the project does

The pipeline reads vehicle or request rows from two source CSV files, reads the provider base from a third CSV, geocodes ZIP codes, computes nearest providers for each vehicle, and writes a final CSV containing the original row plus the Top 3 nearest providers.

The dashboard reads the generated CSV and provides:

- KPIs for the current filtered slice.
- Charts for provider, consultant, regional, and distance distribution.
- A Brazil map view by state.
- A provider summary table.
- A vehicle-level table with sorting, column selection, address copy, and Google Maps route links.
- CSV export for the current filtered slice.
- Browser print or PDF export of the dashboard view.

## Repository structure

- main.py: root entrypoint that calls the official pipeline in src/main.py.
- src/main.py: official processing pipeline.
- src/geocoder.py: ZIP code normalization and geocoding with cache.
- src/distance.py: distance calculation logic using Haversine and OSRM.
- dashboard.html: local dashboard used during development and analysis.
- docs/index.html: published dashboard for GitHub Pages.
- prepare_pages.sh: copies the dashboard and generated CSVs into docs/.
- publish_pages.sh: prepares docs/, syncs a GitHub Pages repository, and pushes the published site.
- Files/: input CSV files.
- cache/: local caches for geocoding and provider matching.
- output/: generated CSV outputs.
- docs/output/: published copies of generated CSV outputs.

## Expected input files

The current pipeline expects these files in Files/:

- Files/Instalação Rastreadores - Agendamentos.csv
- Files/Pendente Instalação - Cartruck.csv
- Files/Instalação Rastreadores - Base Rastradores.csv

### Vehicle sources

The project loads vehicle or request rows from two sources:

- Agendamentos: loaded directly.
- Pendente: loaded with skiprows=1 because the first line is a non-data title row.

Both sources are concatenated into a single vehicle dataset.

### Provider source

The provider base is loaded from the provider CSV and transformed into candidate provider records.

## Business rules

### Vehicle consolidation

- Every row from both vehicle source files is included in the merged dataset.
- An internal _fonte field marks whether the row came from Agendamentos or Pendente.
- The project extracts the vehicle ZIP code from the Endereço field.
- If the ZIP code cannot be extracted or geocoded, the row is written to sem_coordenada.csv.

### ZIP code extraction and normalization

- ZIP codes are extracted from address text using a CEP pattern.
- ZIP codes are normalized to 8 digits by removing punctuation and spaces.
- Provider ZIP codes are normalized from the CEP column.

### City and state inference

- Vehicle city and state are inferred from Endereço when possible.
- This inferred city and state are used to improve geocoding fallback quality.

### Geocoding rules

Vehicle and provider ZIP codes are geocoded with local cache plus external services.

Lookup order:

1. cache/geocode_cache.json
2. BrasilAPI v2 ZIP code endpoint
3. Nominatim fallback

Important behavior:

- Single ZIP geocoding may fall back to Nominatim by ZIP or by city and state.
- Batch geocoding uses BrasilAPI first and only falls back to Nominatim grouped by city and state because public Nominatim is too slow for large volumes.
- When only the city centroid is available, the cache entry is marked as approximate.
- Public Nominatim rate limits are respected.

### Provider candidate rules

- Only providers with coordinates become eligible candidates.
- Provider display name prefers Nome Fantasia; if empty, Nome is used.
- Provider address is rebuilt into a single string from provider address fields.

### Nearest-provider rules

The provider ranking is intentionally two-stage to reduce API usage.

Stage 1:

- Calculate straight-line distance with Haversine against all geocoded providers.
- Keep the closest 15 providers as the shortlist.

Stage 2:

- Query OSRM road distance for the shortlisted providers.
- Return the Top 3 providers ordered by final distance.

Final distance fallback priority:

1. OSRM table distance
2. OSRM route distance when table is invalid or zero
3. Haversine distance as last fallback

### Result cache rules

Provider matching is cached by normalized vehicle ZIP code in cache/results_cache.json.

Important behavior:

- If a ZIP code was already processed, the project reuses the cached Top 3 provider result and avoids new OSRM calls.
- The results cache is versioned.
- If the cache version is outdated, the project ignores it and recalculates.
- If output/resultado_final.csv does not exist, the project forces full recalculation instead of trusting an existing results cache.
- During long runs, the results cache is periodically saved for safer interruption recovery.

### Output rules

The official pipeline writes:

- output/resultado_final.csv: all processable vehicles enriched with Top 3 nearest providers.
- output/sem_coordenada.csv: vehicles that could not be geocoded.

The current official Python pipeline does not generate output/resultado_final.parcial.csv. That file is still supported by the dashboard and publish flow because it may exist from legacy or manual workflows.

## Output schema

resultado_final.csv contains the original vehicle columns plus provider columns for each provider rank.

For each provider rank from 1 to 3, the pipeline appends:

- Prestador_{i}_Nome
- Prestador_{i}_Nome_Legal
- Prestador_{i}_CNPJ_CPF
- Prestador_{i}_Tipo_Fornecedor
- Prestador_{i}_Classificacao
- Prestador_{i}_Endereco
- Prestador_{i}_Cidade
- Prestador_{i}_UF
- Prestador_{i}_CEP
- Prestador_{i}_Distancia_km
- Prestador_{i}_Contato
- Prestador_{i}_Telefone
- Prestador_{i}_Telefone_2
- Prestador_{i}_Email
- Prestador_{i}_Tipos_Veiculos
- Prestador_{i}_Observacao

If fewer than 3 providers are available for a row, the remaining provider fields are written as empty strings.

## Dashboard behavior

The dashboard is a static HTML, CSS, and JavaScript application with no backend.

### Data loading behavior

At startup the dashboard tries to auto-load published data in this order:

1. output/resultado_final.parcial.csv
2. output/resultado_final.csv

If neither file is available, the user can import a folder manually and the dashboard will scan CSV files in that folder.

A CSV is considered compatible only if it contains Prestador_1_Nome.

### Filters and search

The dashboard combines all active filters using AND logic.

Available mechanisms:

- Free text search across all row values.
- Multi-select UF filter.
- Multi-select provider filter based on Prestador_1_Nome.
- Multi-select institution filter.
- Click-to-filter charts for provider, consultant, regional, and distance bucket.
- State map click or state chart bar click also applies UF filter.

Chart filters are cross-filtered. Each chart is rendered against the current filter context excluding its own chart selection, which allows iterative slice refinement.

### State view toggle

The state panel has a **Mapa / Gráfico** segmented toggle. Only one view is visible at a time:

- **Mapa**: Leaflet-powered Brazil choropleth map with color-coded state fill based on vehicle count per UF. Clicking a state toggles its UF in the filter.
- **Gráfico**: Horizontal bar chart of all UFs sorted by count. Clicking a bar toggles its UF in the filter.

Map and chart share the same DOM container (`#stateMapView`). When toggling to chart mode, the Leaflet map instance is destroyed, the container className is changed to `chart-list`, and bars are rendered. When toggling back to map, the className is reset to `map-container map-container--brazil` and a new Leaflet map is initialized.

The map legend is positioned at `bottomleft` and shows discrete color swatches with numerical range labels (e.g. "1–17"). The map pane is shifted 40px right via `margin-left` to avoid legend overlap.

### Provider detail overlay

Clicking a provider bar in the provider chart opens a centered overlay card within the same panel. The card shows:

- Provider name.
- WhatsApp link ("Falar com prestador") if a phone number is detected.
- Raw phone number (as fallback when WhatsApp link cannot be built).
- CPF/CNPJ.
- Titular.
- Estado.
- Endereço as a clickable Google Maps search link.
- Observação.

The overlay closes when:
- The close (×) button is clicked.
- The semi-transparent backdrop is clicked.
- `Escape` key triggers `clearFilters`, which also resets provider selection.

Closing the overlay clears `filterSelections.provider` and `chartSelections.provider`, re-renders the filter menu, and re-applies filters.

### Phone detection

Phone number detection follows a cascade:

1. Exact column name match for `Telefone 1` or `Fone(1)`.
2. Exact column name match for `Telefone 2` or `Fone(2)`.
3. Fuzzy match for columns containing `contato`, `telefone`, `celular`, `tel`, `whatsapp`, `whats`, `fone`, or `phone`.
4. Fallback scan: iterate all columns and pick the first cell whose digits-only length is between 10 and 12.

When building the WhatsApp URL, if the phone number has 10 or 11 digits and does not start with `55`, the international prefix is prepended.

### KPIs

KPIs are based on the current filtered slice:

- Total vehicles.
- Total unique Top 1 providers.
- Total UFs.
- Share of the leading provider in the slice.

### Provider aggregation rule

All provider analytics in the dashboard are based on Prestador_1_Nome, meaning the Top 1 assigned provider for each vehicle.

The provider table shows:

- Provider name.
- CNPJ or CPF.
- Provider UF.
- Number of vehicles assigned to that provider as Top 1.
- Percentage of the current filtered total.

### Distance analysis rule

Distance charts and distance-based filtering use Prestador_1_Distancia_km, which represents the distance between the vehicle and its Top 1 provider.

Current distance buckets:

- 0-30 km
- 31-50 km
- 51-100 km
- 101-250 km
- 251-500 km
- 500+ km

Numeric parsing supports both Brazilian and international decimal or thousand formats before filtering and aggregation.

### Vehicle table behavior

The vehicle table uses the currently filtered rows, then applies local sorting.

Current rules:

- Default sort is Placa ascending.
- If Placa is empty, the dashboard displays Chassi instead.
- When sorting by Placa, rows without an effective Placa or Chassi value are pushed to the end.
- The route column creates a Google Maps driving link from the vehicle address to the Top 1 provider address.
- Address cells are truncated visually, show the full value on hover, and copy the full value on click.
- Friendly labels are applied to some columns, including Prestador_1_Nome to Prestador and Prestador_1_Endereco to Endereço.
- The default visible columns are a curated subset for readability.
- ID Solicitação is not part of the current default visible subset.
- Users can switch between essential columns and all columns.

### Vehicle table limitation

The vehicle table is currently hard-limited to the first 300 rows after filtering and sorting.

This is only a rendering limitation for the table. KPIs, charts, and aggregations still use the full filtered slice.

### Map behavior

- The Brazil map runs client-side.
- It depends on an external GeoJSON loaded at runtime from `https://raw.githubusercontent.com/codeforamerica/click_that_hood/master/public/data/brazil-states.geojson`.
- If the map data is unavailable, the rest of the dashboard still works.
- State fill color is computed from the count ratio relative to the maximum count in the current filtered slice. Five color brackets are used: 0 (inactive), 1–24%, 25–49%, 50–74%, 75–100%.
- The map legend is built dynamically with quantile-like bucket labels (e.g. "0", "1–N", "N–N", "N–N", "N+").
- Clicking a state toggles UF filter selection. Hover shows a tooltip with state name, UF code, and vehicle count.

### Chart behavior

- All charts (provider, consultant, regional, distance, state) show every item — there is no `visibleCount` limit.
- Charts use `.chart-list` CSS class with `max-height: 480px`, `overflow-y: auto`, and `scrollbar-gutter: stable` to enable scrolling when content overflows.
- Each `.bar-row` has `flex-shrink: 0` to prevent flex items from shrinking and hiding the scrollbar.
- Charts with a `chartKey` are clickable: clicking a bar toggles its selection as the chart filter for that axis.
- Clicking a provider bar also synchronizes `filterSelections.provider` and opens the provider detail overlay.

### Export behavior

- CSV export downloads the full filtered slice using the original CSV columns.
- PDF export uses browser printing for the current dashboard view.
- The provider table panel is temporarily hidden during print or PDF export.

## Generated files

### Local outputs

- output/resultado_final.csv
- output/sem_coordenada.csv

Optional or legacy-supported file:

- output/resultado_final.parcial.csv

### Published outputs

prepare_pages.sh copies available output CSVs to docs/output/ and copies dashboard.html to docs/index.html.

The docs/ folder is the static site payload.

## Local setup

### Requirements

- Python 3.
- A local virtual environment at .venv, which is assumed by the scripts.
- Internet access for new geocoding and OSRM route distance calls.
- GitHub CLI gh only if you use the automated publish script.

Current Python dependencies:

- pandas
- requests
- tqdm
- geopy
- python-dotenv

### Install dependencies

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Run the pipeline locally

```bash
.venv/bin/python main.py
```

This run performs the following steps:

1. Load both vehicle CSV sources.
2. Load the provider base.
3. Load and extend the geocode cache.
4. Load and validate the provider-matching results cache.
5. Split rows into geocoded and non-geocoded groups.
6. Process geocoded rows and write the output CSVs.

Expected outputs:

- output/resultado_final.csv
- output/sem_coordenada.csv

## Test locally

### Pipeline test

Run the pipeline and confirm that the output files are regenerated without errors:

```bash
.venv/bin/python main.py
```

### Dashboard test

Use a local HTTP server instead of opening the HTML file directly when you want to validate auto-loading and browser behavior consistently.

Example:

```bash
python3 -m http.server 8000
```

Then open:

- http://localhost:8000/dashboard.html

Why HTTP is recommended:

- Some browsers restrict fetch behavior when opening local files directly.
- The dashboard auto-load logic for output/ files is easier to validate over HTTP.

## Prepare the published site

```bash
./prepare_pages.sh
```

This script:

1. Creates docs/output/ if needed.
2. Copies dashboard.html to docs/index.html.
3. Creates docs/.nojekyll.
4. Removes previously published copies of supported CSV outputs.
5. Copies any available output CSVs into docs/output/.
6. Fails if no output CSV exists in output/.

## Publish

The project uses a separate GitHub Pages repository by default.

Current defaults inside publish_pages.sh:

- Default owner: indianaralopess
- Default fallback repo name when not overridden: verbose-octo-dollop
- Default branch: main
- Default visibility: public

The workflow used in practice in this repository commonly publishes to:

- Repository: upgraded-couscous
- Site URL: https://indianaralopess.github.io/upgraded-couscous/

### Publish existing outputs

```bash
PAGES_REPO_NAME=upgraded-couscous ./publish_pages.sh
```

### Reprocess then publish

```bash
PAGES_REPO_NAME=upgraded-couscous PAGES_RUN_PROCESS=1 ./publish_pages.sh
```

### What publish_pages.sh does

1. Verifies that gh, git, and rsync are installed.
2. Optionally runs the Python pipeline when PAGES_RUN_PROCESS=1.
3. Runs prepare_pages.sh.
4. Creates the GitHub repository if needed.
5. Clones or reuses a sibling local clone of the Pages repository.
6. Synchronizes docs/ into that repository with rsync.
7. Commits and pushes changes.
8. Tries to configure GitHub Pages to publish from the repository root on the selected branch.

### Publish-related environment variables

- PAGES_REPO_NAME: target repository name.
- PAGES_REPO_OWNER: GitHub owner or organization.
- PAGES_REPO_VISIBILITY: public or private when creating the repo.
- PAGES_DEFAULT_BRANCH: branch used for the Pages repository.
- PAGES_REPO_DIR: local path for the cloned Pages repository.
- PAGES_RUN_PROCESS: set to 1 to rerun the Python pipeline before publication.

## Operational notes

- The processing pipeline is local-only. GitHub Pages hosts only static files.
- Any CSV copied to docs/ or pushed to the public Pages repository becomes public.
- Geocoding and OSRM matching depend on external services and network availability.
- The project assumes Brazilian address and CEP conventions.
- Dashboard text and labels are currently mostly in Portuguese even though this README is in English.

## Known limitations

- The dashboard vehicle table renders only the first 300 rows after filter and sort.
- The dashboard uses only the Top 1 provider for most analytics.
- The official pipeline writes resultado_final.csv and sem_coordenada.csv, but not resultado_final.parcial.csv.
- Geocoding quality depends on ZIP code availability and external API completeness.
- City-centroid fallback can introduce approximate coordinates.
- Public OSRM and Nominatim services may rate-limit or temporarily fail.
- PUBLISHING.md still exists in Portuguese, but README.md is the authoritative English reference and should remain aligned with actual code behavior.

## Troubleshooting

### No compatible file appears in the dashboard

Make sure the imported CSV contains Prestador_1_Nome. The dashboard uses that column to detect processed result files.

### Many rows go to sem_coordenada.csv

Check whether Endereço contains a valid CEP pattern and whether the provider and vehicle ZIP codes can be geocoded.

### Results seem outdated

Possible causes:

- cache/results_cache.json is reusing previous ZIP-code matches.
- cache/geocode_cache.json is reusing previous geocoding results.
- docs/output/ still contains previously prepared or published files.

### Published site does not change immediately

GitHub Pages may take a few minutes to redeploy. Confirm GitHub Pages settings if necessary.

## Maintenance rule

Whenever code changes affect processing logic, output columns, dashboard calculations, filters, exports, or publication behavior, update this README in the same change so it remains a reliable source for both people and agents.

## Immutable rules for dashboard edits (dashboard.html and docs/index.html)

These rules must be preserved in any and every modification. A change that violates any of these must be rejected regardless of who or what proposes it.

### File sync rule

- `dashboard.html` and `docs/index.html` must always be kept in functional sync. Any feature, CSS rule, or JS behavior added to one must be mirrored in the other. The only differences allowed are:
  - `docs/index.html` omits `dashboard.html`'s `handleFolderImport` and `fileInput` (folder picker) because GitHub Pages does not support the File System Access API as a folder picker.
  - `dashboard.html` loads CSVs via an `<input type="file" webkitdirectory>` element; `docs/index.html` relies on the auto-load CSV fetch or a simple file input.

### Provider detail overlay rules

- The overlay must be a `<div id="providerDetail">` positioned `position: absolute; inset: 0` over the first `.panel` in the two-column grid, with a semi-transparent `background: rgba(0,0,0,0.25)` backdrop.
- Clicking the overlay background (`e.target === panel`) must close it.
- The overlay must contain a `.provider-detail-card` as the visible card content.
- When the overlay closes, it must clear `filterSelections.provider`, `chartSelections.provider`, and `state.providerDetail`, re-render the provider filter menu, and call `applyFilters()`.

### State view toggle rules

- `#stateMapView` is the single DOM container for both map and chart views. There must never be two separate containers for map and chart.
- When switching to chart mode:
  - The Leaflet map instance must be destroyed (`state.brazilMap.remove(); state.brazilMap = null`).
  - The container className must be set to `"chart-list"`.
  - Inline `style.height` must be cleared (`container.style.height = ""`).
- When switching to map mode:
  - The container className must be reset to `"map-container map-container--brazil"`.
  - A new Leaflet map must be initialized.
- The toggle buttons use `data-view="map"` and `data-view="chart"` attributes.

### Chart rendering rules

- All charts must show every item. No `visibleCount` limit may be reintroduced.
- The `.chart-list` CSS class must always include `max-height: 480px` and `overflow-y: auto` to enable scrolling.
- Every `.bar-row` must have `flex-shrink: 0` to prevent flex items from shrinking.

### Map legend rules

- The legend must be positioned at `bottomleft`.
- The legend must use discrete color swatches (not a continuous gradient bar).
- Each swatch must have a numerical range label above it (e.g. "1–17").
- The map pane must be shifted 40px right via `.leaflet-map-pane { margin-left: 40px }` to avoid legend overlap.

### WhatsApp / Phone rules

- Phone detection must follow the documented cascade: exact match for `Telefone 1`/`Fone(1)`, then `Telefone 2`/`Fone(2)`, then fuzzy match, then fallback cell scan.
- When building the WhatsApp URL, if the number has 10 or 11 digits and does not start with `55`, the prefix must be prepended.
- The WhatsApp icon in the provider detail must use the inline SVG defined in that function. It must NOT be replaced with an external image or icon library.
- The WhatsApp link in the vehicle table must use the inline `whatsappSvgSmall` SVG variable defined in the script.

### Provider chart bar click behavior

- Clicking a provider bar must:
  1. Toggle `chartSelections.provider`.
  2. Sync `filterSelections.provider` to `[chartSelections.provider]` (or `[]` if deselected).
  3. Re-render the provider filter menu.
  4. Set `state.providerDetail` to the selected provider name (or empty).
  5. Call `applyFilters()` (which calls `renderDashboard()` and `renderProviderDetail()`).

### Endereço Google Maps link rules

- The provider detail overlay must render the Endereço field as a clickable Google Maps search link using `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(endereco)}`.
- The route column in the vehicle table must use `https://www.google.com/maps/dir/` with both origin (vehicle address) and destination (provider address).

### CSS architecture rules

- `.chart-list` must remain `display: flex; flex-direction: column` with `gap: 12px`.
- `.bar-row` must remain `display: grid; grid-template-columns: minmax(160px, 1.2fr) 2.2fr auto; gap: 12px; align-items: center`.
- The map container must use Leaflet. No other mapping library may be substituted.
- The map container IDs must remain `#stateMapView` and `#providerChart`. These IDs are referenced by both CSS and JavaScript throughout the file.


# Como usar

## Rodar o pipeline

### Opção 1 — Dois cliques (recomendado)
1. Abra a pasta do projeto no Finder
2. Dê dois cliques em `rodar.command`
3. O Terminal abre, arraste o XLSX e pronto

### Opção 2 — Pelo terminal
```bash
source .venv/bin/activate
python3 src/main2.py
```

### Opção 3 — De qualquer lugar (uma linha)
```bash
curl -fsSL https://raw.githubusercontent.com/Indianara/tato-projects/main/install.sh | bash -s -- /caminho/planilha.xlsx
```

---

# Como fazer alterações no código e atualizar o GitHub

Você é dona do repositório, então pode escolher entre **push direto** (mais simples) ou **Pull Request** (mais seguro).

## Método 1 — Push direto (simples, sem PR)

Use quando for uma alteração rápida que você mesma fez:

```bash
# 1. Ver o que mudou
git status

# 2. Adicionar os arquivos alterados
git add .

# 3. Criar o commit
git commit -m "descricao do que mudou"

# 4. Enviar para o GitHub
git push origin main
```

Pronto. O repositório já está atualizado.

## Método 2 — Pull Request (recomendado para mudanças maiores)

Usar quando quiser revisar antes de publicar, ou quando outra pessoa sugerir alterações:

```bash
# 1. Criar uma branch para sua alteração
git checkout -b minha-mudanca

# 2. Fazer as alterações nos arquivos...

# 3. Adicionar e commitar
git add .
git commit -m "descricao da mudanca"

# 4. Enviar a branch para o GitHub
git push origin minha-mudanca
```

Depois, no navegador:

1. Acesse https://github.com/Indianara/tato-projects
2. Vai aparecer um aviso: **"minha-mudanca had recent pushes"**
3. Clique em **"Compare & pull request"**
4. Escreva um título e descrição
5. Clique em **"Create pull request"**
6. Revise as alterações na aba **"Files changed"**
7. Clique em **"Merge pull request"** → **"Confirm merge"**
8. Pronto, a alteração está no `main`

### Para atualizar seu computador depois do merge:
```bash
git checkout main
git pull origin main
```

## Método 3 — Atalho: pelo site do GitHub (sem terminal)

Para alterações pequenas (ex: ajustar README):

1. Acesse https://github.com/Indianara/tato-projects
2. Navegue até o arquivo que quer alterar
3. Clique no ícone ✏️ (lápis) no canto superior direito
4. Faça a edição
5. Lá embaixo, escreva um título para a mudança
6. Escolha **"Create a new branch for this commit"**
7. Clique em **"Propose changes"**
8. Depois clique em **"Create Pull Request"** e **"Merge Pull Request"**

---

## Resumo dos comandos do dia a dia

```bash
# Atualizar seu computador com o que está no GitHub
git pull origin main

# Ver o que foi alterado
git status
git diff

# Commitar e enviar (push direto)
git add .
git commit -m "mensagem"
git push origin main
```

## Repositórios

| Projeto | URL |
|---|---|
| Código fonte | https://github.com/Indianara/tato-projects |
| Site publicado | https://indianara.github.io/tato-projects/ |


cd /Users/indianarasantos/Documents/Developments/Extensions/PrestadorMaisProximo && \
git add -A && \
git commit -m "atualizacao- Abrir site automaticamente $(date '+%Y-%m-%d')" && \
git push origin main