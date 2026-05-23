"""PyInstaller build script for 可交互调车系统"""

import subprocess
import sys


def build():
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "可交互调车系统",
        "--onefile",
        "--noconsole",
        "--clean",
        "--add-data", "app/ui/styles/theme.qss;app/ui/styles",
        "--hidden-import", "pyqtgraph",
        "--hidden-import", "flask",
        "--hidden-import", "flask_socketio",
        "--hidden-import", "engineio",
        "--hidden-import", "socketio",
        "--hidden-import", "qt_material",
        "--exclude-module", "PySide6",
        "--exclude-module", "PySide2",
        "--exclude-module", "PyQt6",
        "--exclude-module", "shiboken6",
        "--exclude-module", "matplotlib",
        "--exclude-module", "tkinter",
        "--exclude-module", "IPython",
        "--exclude-module", "jupyter",
        "--exclude-module", "zmq",
        "--exclude-module", "PIL",
        "--exclude-module", "numpy",
        "--exclude-module", "scipy",
        "--exclude-module", "pandas",
        "--exclude-module", "cryptography",
        "--exclude-module", "sqlite3",
        "--exclude-module", "setuptools",
        "--exclude-module", "pyarrow",
        "--exclude-module", "botocore",
        "--exclude-module", "boto3",
        "--exclude-module", "openpyxl",
        "--exclude-module", "lxml",
        "--exclude-module", "sqlalchemy",
        "--exclude-module", "tables",
        "--exclude-module", "fsspec",
        "--exclude-module", "chardet",
        "--exclude-module", "charset_normalizer",
        "--exclude-module", "certifi",
        "--exclude-module", "urllib3",
        "--exclude-module", "requests",
        "--exclude-module", "pytest",
        "--exclude-module", "qtpy",
        "--exclude-module", "h5py",
        "--exclude-module", "numba",
        "--exclude-module", "llvmlite",
        "--exclude-module", "pythoncom",
        "--exclude-module", "win32com",
        "--exclude-module", "pywintypes",
        "app/main.py",
    ]

    print("Building 可交互调车系统.exe ...")
    subprocess.run(cmd, check=True)
    print("\nBuild complete! Output: dist/可交互调车系统.exe")


if __name__ == "__main__":
    build()
