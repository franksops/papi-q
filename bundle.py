import os
import re
import sys

def bundle():
    """Consolidate src/ modules into a single papi-q.py file with a universal bootstrapper."""
    
    files = [
        "src/constants.py",
        "src/logger.py",
        "src/config.py",
        "src/api.py",
        "src/audit.py",
        "src/utils.py",
        "src/ui/session.py",
        "src/ui/components.py",
        "src/main.py",
    ]
    
    output_path = "papi-q.py"
    print(f"Bundling {len(files)} files into {output_path}...")
    
    with open(output_path, "w") as out:
        out.write('''#!/usr/bin/env python3
"""
SmartQuota Manager - Universal Single-File Distribution
Optimized for OneFS 9.12.0.1
"""
import sys
import os
import subprocess
import platform
import shutil
import glob
import json
import csv
import time
import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

# Python Version Check
if sys.version_info < (3, 8):
    print("Error: Python 3.8 or higher is required.")
    sys.exit(1)

def run_command(cmd, shell=False):
    try:
        subprocess.check_call(cmd, shell=shell)
        return True
    except subprocess.CalledProcessError:
        return False

def bootstrap():
    """Ensure dependencies are met using the best available stable Python version."""
    config_dir = (Path.home() / ".papi-q").resolve()
    venv_dir = config_dir / "venv"
    config_dir.mkdir(parents=True, exist_ok=True)
    
    current_prefix = Path(sys.prefix).resolve()
    in_venv = current_prefix == venv_dir.resolve()

    # If we aren't in a venv yet, let's find the best Python to use
    if not in_venv:
        best_python = sys.executable
        # If current is 3.14+, search for stable fallbacks
        if sys.version_info >= (3, 14):
            for version in ["3.13", "3.12", "3.11"]:
                path = shutil.which(f"python{version}")
                if path:
                    print(f"[*] Experimental Python detected. Switching to stable: {path}")
                    best_python = path
                    break
        
        if not venv_dir.exists():
            print(f"[*] Creating stable virtual environment in {venv_dir}...")
            if not run_command([best_python, "-m", "venv", str(venv_dir)]):
                print(f"Error: Failed to create venv with {best_python}")
                sys.exit(1)
        
        venv_python = str(venv_dir / "bin" / "python") if os.name != "nt" else str(venv_dir / "Scripts" / "python.exe")
        
        # Verify if the venv is actually using a stable version
        # If the venv exists but was built with 3.14, we should recreate it
        res = subprocess.run([venv_python, "--version"], capture_output=True, text=True)
        if "3.14" in res.stdout and sys.version_info < (3, 14):
            print("[!] Existing venv is 3.14. Recreating with stable Python...")
            shutil.rmtree(venv_dir)
            return bootstrap() # Recurse once to recreate

        print("[*] Syncing dependencies in virtual environment...")
        run_command([venv_python, "-m", "pip", "install", "--upgrade", "pip"])
        deps = ["isilon-sdk", "streamlit", "pandas", "urllib3", "python-dotenv"]
        if not run_command([venv_python, "-m", "pip", "install"] + deps):
            run_command([venv_python, "-m", "pip", "install", "--break-system-packages"] + deps)

        print("\\n[+] Environment ready. Re-launching...\\n")
        os.execv(venv_python, [venv_python] + sys.argv)

    # If we are in the venv, verify imports
    deps_map = {"streamlit": "streamlit", "isi_sdk": "isilon-sdk", "pandas": "pandas", "urllib3": "urllib3", "dotenv": "python-dotenv"}
    missing = []
    for mod, pkg in deps_map.items():
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    
    if missing:
        print(f"\\n[!] Critical: Dependencies missing inside venv ({sys.version.split()[0]})")
        print(f"[*] Try: {sys.executable} -m pip install " + " ".join(missing))
        sys.exit(1)

    return True

if "__main__" == __name__ and not os.environ.get("STREAMLIT_RUNNING"):
    bootstrap()
    os.environ["STREAMLIT_RUNNING"] = "1"
    subprocess.run([sys.executable, "-m", "streamlit", "run", __file__])
    sys.exit(0)

import streamlit as st
import pandas as pd
import urllib3
try:
    import isi_sdk
except ImportError:
    pass

# --- APP LOGIC START ---
''')

        for file_path in files:
            with open(file_path, "r") as f:
                content = f.read()
                content = re.sub(r'^from src\..* import .*$', '', content, flags=re.MULTILINE)
                content = re.sub(r'^import .* as state$', 'from streamlit import session_state as state', content, flags=re.MULTILINE)
                content = re.sub(r'^from src import .*$', '', content, flags=re.MULTILINE)
                content = re.sub(r'^from audit import .*$', '', content, flags=re.MULTILINE)
                content = re.sub(r'^from utils import .*$', '', content, flags=re.MULTILINE)
                content = re.sub(r'^"""[\s\S]*?"""', '', content, count=1)
                
                out.write(f"\n# --- Source: {file_path} ---\n")
                out.write(content)
                out.write("\n")

        out.write('''
# --- ENTRY POINT ---
if __name__ == "__main__":
    main()
''')

    print(f"Successfully created {output_path}")
    os.chmod(output_path, 0o755)

if __name__ == "__main__":
    bundle()
