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
        if sys.version_info >= (3, 14):
            for version in ["3.13", "3.12", "3.11"]:
                path = shutil.which(f"python{version}")
                if path:
                    print(f"[*] Switching to stable Python: {path}")
                    best_python = path
                    break
        
        if not venv_dir.exists():
            print(f"[*] Creating virtual environment in {venv_dir}...")
            run_command([best_python, "-m", "venv", str(venv_dir)])
        
        venv_python = str(venv_dir / "bin" / "python") if os.name != "nt" else str(venv_dir / "Scripts" / "python.exe")
        
        # If the venv exists but is 3.14, wipe it
        res = subprocess.run([venv_python, "--version"], capture_output=True, text=True)
        if "3.14" in res.stdout and sys.version_info < (3, 14):
            print("[!] Wiping incompatible 3.14 venv...")
            shutil.rmtree(venv_dir)
            return bootstrap()

        print("[*] Syncing dependencies (fresh install)...")
        run_command([venv_python, "-m", "pip", "install", "--upgrade", "pip"])
        deps = ["isilon-sdk", "streamlit", "pandas", "urllib3", "python-dotenv"]
        # Use --no-cache-dir to ensure we aren't pulling a corrupt build
        run_command([venv_python, "-m", "pip", "install", "--no-cache-dir"] + deps)

        print("\\n[+] Environment ready. Re-launching...\\n")
        os.execv(venv_python, [venv_python] + sys.argv)

    # --- VERIFICATION PHASE (Inside Venv) ---
    deps_map = {"streamlit": "streamlit", "isi_sdk": "isilon-sdk", "pandas": "pandas", "urllib3": "urllib3", "dotenv": "python-dotenv"}
    missing = []
    for mod, pkg in deps_map.items():
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    
    if missing:
        # Check if we are in a 'Zombie' state (pip thinks they exist, but python can't find them)
        print(f"\\n[!] Detected inconsistent environment ({sys.version.split()[0]})")
        print(f"[*] Missing modules: {', '.join(missing)}")
        
        if not os.environ.get("PAPI_RETRY"):
            print("[*] Attempting Nuclear Recovery (wiping venv)...")
            shutil.rmtree(venv_dir)
            os.environ["PAPI_RETRY"] = "1"
            # Launch original python to recreate everything
            orig_python = shutil.which("python3") or sys.executable
            os.execv(orig_python, [orig_python] + sys.argv)
        else:
            print("\\n[!] Recovery failed. Please try: rm -rf ~/.papi-q/venv")
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
