"""
Empacota run.py como aplicativo macOS (.app).

Uso:
    # Instalar py2app
    pip install py2app

    # Limpar builds anteriores
    rm -rf build dist

    # Gerar .app
    python setup.py py2app

    # Gerar .dmg
    hdiutil create -volname "PrestadorMaisProximo" \
        -srcfolder dist/PrestadorMaisProximo.app \
        -ov -format UDZO \
        "dist/PrestadorMaisProximo.dmg"

O .app gerado estara em: dist/PrestadorMaisProximo.app
O .dmg gerado estara em: dist/PrestadorMaisProximo.dmg
"""

import sys
from setuptools import setup

APP = ["run.py"]
APP_NAME = "PrestadorMaisProximo"

OPTIONS = {
    "argv_emulation": True,
    "iconfile": "icon.icns",
    "packages": [
        "pandas",
        "requests",
        "geopy",
        "tqdm",
        "openpyxl",
    ],
    "excludes": [
        "PyQt5", "PyQt6", "PySide2", "PySide6",
        "tkinter", "matplotlib", "scipy", "notebook",
        "streamlit", "altair", "pydeck",
        "starlette", "uvicorn", "websockets",
    ],
    "plist": {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleIdentifier": f"com.Indianara.{APP_NAME}",
        "NSHighResolutionCapable": True,
    },
    "resources": [
        "Files",
        "src",
    ],
}

setup(
    name=APP_NAME,
    app=APP,
    options={"py2app": OPTIONS},
    data_files=[
        ("Files", ["Files/Base Prestadores.csv", "Files/CEPs_Corrigidos.csv"]),
    ],
    setup_requires=["py2app"],
)
