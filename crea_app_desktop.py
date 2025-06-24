import os
import shutil
import subprocess
import sys

for folder in ["dist", "build", "__pycache__"]:
    if os.path.exists(folder):
        shutil.rmtree(folder)

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onedir",
    "--windowed",
    "--hidden-import=flask",
    "--hidden-import=werkzeug",
    "--hidden-import=jinja2",
    "--hidden-import=markupsafe",
    "--hidden-import=itsdangerous",
    "--hidden-import=click",
    "--icon=static/favicon.ico",
    "app_desktop.py"
]
subprocess.run(cmd) 