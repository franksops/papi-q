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
    """Ensure all system and python dependencies are met."""
    system = platform.system().lower()
    missing_deps = []
    
    try:
        import streamlit
        import isi_sdk
        import pandas
        import urllib3
    except ImportError:
        missing_deps = ["isilon-sdk", "streamlit", "pandas", "urllib3", "python-dotenv"]

    if not missing_deps:
        return True

    print(f"\\n[!] Missing Python dependencies: {', '.join(missing_deps)}")
    choice = input("Would you like to attempt auto-installation? [y/N]: ").lower()
    if choice != 'y':
        print("Manual install required: pip install " + " ".join(missing_deps))
        sys.exit(1)

    if system == "darwin": # macOS
        if shutil.which("brew"):
            print("[*] Ensuring python3 is available via brew...")
            run_command(["brew", "install", "python"])
    
    elif system == "linux":
        if shutil.which("apt-get"):
            run_command(["sudo", "apt-get", "update", "-y"])
            run_command(["sudo", "apt-get", "install", "-y", "python3-pip"])
        elif shutil.which("dnf"):
            run_command(["sudo", "dnf", "install", "-y", "python3-pip"])

    print("[*] Installing python dependencies via pip...")
    pip_cmd = [sys.executable, "-m", "pip", "install"] + missing_deps
    if not run_command(pip_cmd):
        run_command(pip_cmd + ["--user"])

    print("\\n[+] Done. Re-launching...\\n")
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
