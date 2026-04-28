# 📊 SmartQuota Manager for Dell PowerScale

**SmartQuota Manager** is a professional-grade, high-performance management suite designed for Storage Administrators to monitor and manage Dell PowerScale (Isilon) clusters running **OneFS 9.12.0.1**. It provides a 360-degree view of filesystem objects, including Quotas, Snapshots, and ACLs.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/streamlit-1.32+-orange.svg)](https://streamlit.io/)
[![OneFS](https://img.shields.io/badge/OneFS-9.12.0.1-green.svg)](https://www.dell.com/support/manuals/en-us/isilon-onefs/)

---

## 🚀 Key Features

- **Single-File Distribution**: Run the entire app from a single self-contained file: `papi-q.py`.
- **Universal Object Manager**: A dynamic property grid that allows you to view and modify *any* API-exposed quota property.
- **Full Quota Lifecycle (CRUD)**: Create, Read, Update, and Delete quotas directly from the UI.
- **Filesystem Insights**:
    - **Snapshot Viewer**: View all snapshots associated with a specific path.
    - **ACL Inspector**: Detailed view of Owner, Group, and Access Control Entries (ACEs).
- **Multi-Cluster Support**: Manage 6+ clusters with easy switching or custom URL entry.
- **Bulk Export**: Generate human-readable CSV reports for all quotas, filtered by Access Zone or Protocol (SMB/NFS).
- **Audit Logging**: Comprehensive CSV logging of all administrative actions for compliance.
- **Universal Bootstrapper**: Automated environment setup for macOS (Homebrew) and Linux (apt/dnf).

---

## 📦 Installation & Setup

### The Universal Way (Recommended)
You don't need to manually install dependencies or set up virtual environments. Simply download `papi-q.py` and run it:

```bash
python3 papi-q.py
```

**What happens next?**
1. **OS Detection**: The script identifies if you are on macOS or Linux.
2. **System Bootstrap**: It checks for system-level requirements and offers to install them (e.g., `brew install python` or `apt install python3-pip`).
3. **Python Bootstrap**: It automatically installs `isilon-sdk`, `streamlit`, `pandas`, and other requirements.
4. **Auto-Launch**: The Streamlit web interface launches automatically.

---

## 🔐 Authentication

1. **Cluster Selection**: Choose a pre-defined cluster from `clusters.json` or select **"Custom URL..."** to enter a manual IP/FQDN (e.g., `https://isilon.local:8080`).
2. **Credentials**: 
    - Supports local cluster accounts.
    - Supports Active Directory accounts in **`domain\user`** format.
3. **SSL**: Option to ignore SSL certificates for internal management networks.

---

## 🗺️ Navigation & Usage

The application is organized into 5 intuitive tabs:

### 1. 📈 Monitoring (Dashboard)
- View **Top Offenders** categorised by usage (Critical >90%, Warning >80%).
- Search and filter the full quota inventory by Share Name, Path, or Access Zone.
- **Action**: Select a quota row to "focus" on it for the Universal Manager.

### 2. 🔧 Modify (Universal Object Manager)
This is the "Swiss Army Knife" for existing quotas:
- **Quota Settings**: An editable grid of every property returned by the API. Toggle flags, change limits, or update comments.
- **Snapshots**: View real-time snapshot data linked to the path.
- **Permissions**: Inspect the security descriptor (ACLs) to troubleshoot access issues.
- **Decommission**: Securely delete the quota with a text-confirmation challenge.

### 3. ➕ Create (Provisioning)
- Form-based interface to create new Directory, User, Group, or Default quotas.
- Specify paths, limits, enforcement flags, and Access Zones.

### 4. 📥 Export (Reporting)
- Generate full cluster reports.
- Filter exports by **Access Zone** or **Protocol** (the tool automatically cross-references SMB shares and NFS exports to tag quotas).

### 5. 📜 Audit Log
- Review the recent history of all changes made via the tool on the current machine.

---

## 🛠️ Development

### Project Structure
```
papi-q/
├── papi-q.py           # Universal Single-File Distribution (Run this!)
├── bundle.py           # Build script to generate papi-q.py from src/
├── clusters.json       # Cluster inventory configuration
├── DOCS.md             # Detailed technical documentation
├── src/                # Modular source code
│   ├── api.py          # Refined OneFS API Bridge (v9.12.0.1)
│   ├── main.py         # Primary Streamlit UI Logic
│   ├── ui/             # Reusable UI Components & Session Management
│   └── utils.py        # Formatting and pagination utilities
└── README.md           # This file
```

### Building the Bundle
If you modify any file in the `src/` directory, update the single-file distribution by running:
```bash
python3 bundle.py
```

---

## 📚 Technical Background

- **Backend**: Uses the Dell PowerScale Platform API (PAPI) via the official `isilon-sdk`.
- **Target Version**: Optimized for **OneFS 9.12.0.1**.
- **Audit Trail**: Local `audit.csv` maintains an append-only record of changes.

---

## ⚖️ License & Support

Licensed under the MIT License. For feature requests or issues, please contact the storage administration team or file an issue in the repository.

*Maintained by [FranksOps](https://github.com/franksops)*
