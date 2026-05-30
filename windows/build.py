"""PyInstaller build — EdgeHub with Vue 3 frontend."""

import PyInstaller.__main__
import os, sys

APP_NAME = "EdgeHub"
ENTRY = os.path.join("app", "main.py")

args = [
    ENTRY,
    "--name", APP_NAME,
    "--onefile",
    "--windowed",
    "--clean",
    "--add-data", f"frontend/dist{os.pathsep}frontend/dist",
    "--hidden-import", "uvicorn.logging",
    "--hidden-import", "uvicorn.loops.auto",
    "--hidden-import", "uvicorn.protocols.http.auto",
    "--collect-all", "fastapi",
]

PyInstaller.__main__.run(args)
