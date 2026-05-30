"""PyInstaller build script for EdgeHub Windows Client."""

import PyInstaller.__main__
import os
import sys

APP_NAME = "EdgeHub"
ENTRY = os.path.join("app", "main.py")

args = [
    ENTRY,
    "--name", APP_NAME,
    "--onefile",
    "--windowed",
    "--clean",
    "--add-data", f"app/ui/styles{os.pathsep}ui/styles",
    "--hidden-import", "qfluentwidgets",
    "--hidden-import", "PyQt5.QtWebSockets",
    "--hidden-import", "PyQt5.QtWebChannel",
]

if sys.platform == "win32":
    args += ["--icon", "app/ui/styles/edgehub.ico"]

PyInstaller.__main__.run(args)
