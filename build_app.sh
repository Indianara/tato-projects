#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

APP_NAME="PrestadorMaisProximo"

echo "=== Build $APP_NAME ==="
echo ""

# 1. Verificar / instalar py2app
if ! python -c "import py2app" 2>/dev/null; then
    echo "[1/5] Instalando py2app..."
    pip install py2app
else
    echo "[1/5] py2app ja instalado"
fi

# 2. Limpar builds anteriores
echo "[2/5] Limpando builds anteriores..."
rm -rf build dist

# 3. Gerar .app
echo "[3/5] Gerando $APP_NAME.app..."
python setup.py py2app

# 4. Verificar se gerou
APP_PATH="dist/$APP_NAME.app"
if [ ! -d "$APP_PATH" ]; then
    echo "ERRO: .app nao foi gerado em $APP_PATH"
    exit 1
fi
echo "  App gerado: $APP_PATH"

# 5. Gerar .dmg
DMG_PATH="dist/$APP_NAME.dmg"
echo "[4/5] Gerando $DMG_PATH..."
hdiutil create -volname "$APP_NAME" \
    -srcfolder "$APP_PATH" \
    -ov -format UDZO \
    "$DMG_PATH"

echo ""
echo "[5/5] Build concluido!"
echo "  .app: $APP_PATH"
echo "  .dmg: $DMG_PATH"
echo ""
echo "Para distribuir, envie o arquivo .dmg"
