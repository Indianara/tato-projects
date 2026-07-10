# Publicar no GitHub Pages

## Estrutura criada

- `dashboard.html`: dashboard principal para desenvolvimento local.
- `prepare_pages.sh`: gera a versão estática pronta para publicação.
- `docs/`: pasta de saída para GitHub Pages.

O dashboard publicado tenta carregar automaticamente um dos arquivos abaixo, nesta ordem:

- `output/resultado_final.parcial.csv`
- `output/resultado_final.csv`

Se nenhum existir no site publicado, ele continua aceitando importação manual da pasta de CSVs.

## Fluxo de atualização

1. Reprocesse localmente os dados.
2. Gere a pasta de publicação:

```bash
./prepare_pages.sh
```

3. Publique a pasta `docs/`.

## Publicação com um único comando

O projeto agora inclui o script `publish_pages.sh`.

Ele faz tudo em sequência:

1. Usa os arquivos já existentes em `output/`.
2. Gera a pasta `docs/`.
3. Cria o repositório público no GitHub, se ele ainda não existir.
4. Clona o repositório publicado em uma pasta irmã do projeto.
5. Sincroniza os arquivos do site.
6. Faz commit e push.

Comando padrão:

```bash
chmod +x publish_pages.sh prepare_pages.sh
./publish_pages.sh
```

Configuração atual padrão:

```text
Conta: indianaralopess
Repositório: upgraded-couscous
URL final: https://indianaralopess.github.io/upgraded-couscous/
```

Variáveis opcionais:

```bash
PAGES_REPO_NAME=outro-repo ./publish_pages.sh
PAGES_REPO_OWNER=outra-conta ./publish_pages.sh
PAGES_RUN_PROCESS=1 ./publish_pages.sh
```

Se você quiser republicar exatamente o resultado que já está na pasta `output/`, basta rodar o script sem nenhuma variável extra.

Se quiser forçar um novo processamento antes da publicação:

```bash
PAGES_RUN_PROCESS=1 ./publish_pages.sh
```

## Opção A: publicar neste mesmo repositório

Use essa opção apenas se tudo que está neste repositório puder ficar público.

1. Suba este repositório para sua conta pessoal no GitHub.
2. Faça commit da pasta `docs/`.
3. No GitHub, abra `Settings > Pages`.
4. Em `Build and deployment`, escolha `Deploy from a branch`.
5. Selecione a branch principal e a pasta `/docs`.
6. Salve.

URL esperada:

```text
https://SEU-USUARIO.github.io/NOME-DO-REPOSITORIO/
```

## Opção B: publicar em um repositório separado

Essa é a opção recomendada se você não quer expor o código Python, cache ou arquivos de entrada.

1. Crie um novo repositório público na sua conta pessoal, por exemplo `prestador-mais-proximo-site`.
2. Rode `./prepare_pages.sh` neste projeto.
3. Copie o conteúdo da pasta `docs/` para a raiz do novo repositório.
4. Faça commit e push nesse novo repositório.
5. No GitHub, abra `Settings > Pages`.
6. Em `Build and deployment`, escolha `Deploy from a branch`.
7. Selecione a branch principal e a pasta `/ (root)`.
8. Salve.

URL esperada:

```text
https://SEU-USUARIO.github.io/prestador-mais-proximo-site/
```

## Comandos sugeridos

Processar os dados:

```bash
.venv/bin/python main.py
```

Gerar a pasta publicável:

```bash
chmod +x prepare_pages.sh
./prepare_pages.sh
```

## Observações importantes

- GitHub Pages publica apenas conteúdo estático. O Python continua rodando só na sua máquina.
- Se o repositório publicado for público, qualquer CSV incluído nele também ficará público.
- O mapa do Brasil depende de um arquivo GeoJSON externo carregado em tempo de execução; isso continua funcionando em Pages.