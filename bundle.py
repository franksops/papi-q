import os
import re
import sys

def bundle():
    """Consolidate src/ modules into a single papi-q.py file with a universal bootstrapper."""
    
    # Files to include in order of dependency
    files = [
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
        # 1. Header and Bootstrapping logic
        out.write('''#!/usr/bin/env python3
"""
SmartQuota Manager - Universal Single-File Distribution
OneFS 9.12.0.1 Optimized
"""
import sys
import os
import subprocess
import platform
import shutil
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum
import json
import csv
import time
from datetime import datetime
from pathlib import Path

def run_command(cmd, shell=False):
    """Run a shell command and return success."""
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
        print("Installation cancelled. Please run: pip install " + " ".join(missing_deps))
        sys.exit(1)

    # 1. System Level Installation
    if system == "darwin": # macOS
        if not shutil.which("brew"):
            print("[*] Homebrew not found. Please install Homebrew: https://brew.sh/")
        else:
            print("[*] macOS detected. Ensuring python3 is available via brew...")
            run_command(["brew", "install", "python"])
    
    elif system == "linux":
        if shutil.which("apt-get"):
            print("[*] Debian/Ubuntu detected. Installing pip...")
            run_command(["sudo", "apt-get", "update", "-y"])
            run_command(["sudo", "apt-get", "install", "-y", "python3-pip"])
        elif shutil.which("dnf"):
            print("[*] RHEL/CentOS/Fedora detected. Installing pip...")
            run_command(["sudo", "dnf", "install", "-y", "python3-pip"])
        elif shutil.which("yum"):
            print("[*] Older RHEL/CentOS detected. Installing pip...")
            run_command(["sudo", "yum", "install", "-y", "python3-pip"])

    # 2. Python Level Installation
    print("[*] Installing python dependencies via pip...")
    pip_cmd = [sys.executable, "-m", "pip", "install"] + missing_deps
    if not run_command(pip_cmd):
        print("[!] Pip installation failed. Trying with --user...")
        run_command(pip_cmd + ["--user"])

    print("\\n[+] Dependencies installed successfully. Re-launching...\\n")
    return True

# Run Bootstrapper
if "__main__" == __name__ and not os.environ.get("STREAMLIT_RUNNING"):
    bootstrap()
    os.environ["STREAMLIT_RUNNING"] = "1"
    # Ensure we use the streamlit module to run the script
    subprocess.run([sys.executable, "-m", "streamlit", "run", __file__])
    sys.exit(0)

# Import dependencies after bootstrap
import streamlit as st
import pandas as pd
import urllib3
try:
    import isi_sdk
except ImportError:
    pass # Handled by bootstrap, but needed for type hinting/imports in main body

# --- APP LOGIC START ---
''')

        # 2. Process each file
        for file_path in files:
            print(f"  Processing {file_path}...")
            with open(file_path, "r") as f:
                content = f.read()
                
                # Strip out relative imports and module docstrings
                content = re.sub(r'^from src\..* import .*$', '', content, flags=re.MULTILINE)
                content = re.sub(r'^import .* as state$', 'from streamlit import session_state as state', content, flags=re.MULTILINE)
                content = re.sub(r'^from src import .*$', '', content, flags=re.MULTILINE)
                content = re.sub(r'^from audit import .*$', '', content, flags=re.MULTILINE)
                
                # Remove module-level docstrings if they exist at the top
                content = re.sub(r'^"""[\s\S]*?"""', '', content, count=1)
                
                out.write(f"\n# --- Source: {file_path} ---\n")
                out.write(content)
                out.write("\n")

        # 3. Footer
        out.write('''
# --- ENTRY POINT ---
if __name__ == "__main__":
    # This part only runs inside the Streamlit context
    main()
''')

    print(f"Successfully created {output_path}")
    # Make it executable
    os.chmod(output_path, 0o755)

if __name__ == "__main__":
    bundle()
