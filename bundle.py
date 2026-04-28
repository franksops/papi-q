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
    """Ensure all system and python dependencies are met using a managed venv."""
    config_dir = (Path.home() / ".papi-q").resolve()
    venv_dir = config_dir / "venv"
    config_dir.mkdir(parents=True, exist_ok=True)
    
    # Robust venv detection using resolved paths
    current_prefix = Path(sys.prefix).resolve()
    in_venv = current_prefix == venv_dir.resolve()
    
    # DEBUG: Help identify why detection might fail on new Python versions
    if os.environ.get("DEBUG_PAPI"):
        print(f"[*] Debug: prefix={current_prefix}")
        print(f"[*] Debug: venv_dir={venv_dir.resolve()}")
        print(f"[*] Debug: in_venv={in_venv}")

    deps = {
        "streamlit": "streamlit",
        "isi_sdk": "isilon-sdk",
        "pandas": "pandas",
        "urllib3": "urllib3",
        "dotenv": "python-dotenv"
    }
    
    missing_pkg = []
    for mod, pkg in deps.items():
        try:
            __import__(mod)
        except (ImportError, Exception) as e:
            missing_pkg.append(pkg)
            if in_venv:
                print(f"[*] Dependency Error: Failed to import {mod} ({pkg}) -> {e}")

    if not missing_pkg:
        return True

    # If we are in the venv and still missing pkgs, it's a critical failure
    if in_venv:
        print(f"\\n[!] Critical: Dependencies missing inside virtual environment.")
        print(f"[!] Missing: {', '.join(missing_pkg)}")
        print(f"[*] Try manual fix: {sys.executable} -m pip install " + " ".join(missing_pkg))
        sys.exit(1)

    print(f"\\n[!] Missing Python dependencies: {', '.join(missing_pkg)}")
    
    if not venv_dir.exists():
        print(f"[*] Creating virtual environment in {venv_dir}...")
        if not run_command([sys.executable, "-m", "venv", str(venv_dir)]):
            print("Error: Failed to create virtual environment.")
            sys.exit(1)
    
    venv_python = str(venv_dir / "bin" / "python") if os.name != "nt" else str(venv_dir / "Scripts" / "python.exe")
    print("[*] Syncing dependencies in virtual environment...")
    
    # Ensure pip is up to date first
    run_command([venv_python, "-m", "pip", "install", "--upgrade", "pip"])
        
    if not run_command([venv_python, "-m", "pip", "install"] + list(deps.values())):
        # Fallback for systems with tight constraints
        run_command([venv_python, "-m", "pip", "install", "--break-system-packages"] + list(deps.values()))

    print("\\n[+] Environment ready. Re-launching...\\n")
    os.execv(venv_python, [venv_python] + sys.argv)
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
