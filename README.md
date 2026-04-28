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
- **Auto-Saving Clusters**: Successful logins via custom URLs are automatically saved to your inventory.
- **Bulk Export**: Generate human-readable CSV reports for all quotas, filtered by Access Zone or Protocol (SMB/NFS).
- **Graceful Shutdown**: Securely stop the application server directly from the GUI.
- **Daily Audit Logging**: Automatic rotation of cluster-specific audit logs named `hostname_MMDDYEAR.csv`.
- **System-Level Logging**: Comprehensive startup and error logging to `system.log` for easier troubleshooting.
- **Integrated Docs**: Direct links to **Official Dell Documentation** for every management task.
- **Universal Bootstrapper**: Automated environment setup for macOS (Homebrew) and Linux (apt/dnf).

---

## 📦 Installation & Setup

### The Universal Way (Recommended)
The fastest way to deploy this to a new jump box is via `curl`. This command downloads the self-bootstrapping script and launches it immediately:

```bash
curl -L -o papi-q.py https://raw.githubusercontent.com/franksops/papi-q/gemini/papi-q.py && python3 papi-q.py
```

**What happens next?**
1. **OS Detection**: The script identifies if you are on macOS or Linux.
2. **System Bootstrap**: It checks for system-level requirements and offers to install them (e.g., `brew install python` or `apt install python3-pip`).
3. **Python Bootstrap**: It automatically installs `isilon-sdk`, `streamlit`, `pandas`, and other requirements in the background.
4. **Auto-Launch**: The Streamlit web interface launches automatically.

---

## 🔐 Authentication

1. **Cluster Selection**: Choose a saved cluster or enter a raw **IP or Hostname**.
    - **Smart URL**: Enter `10.1.1.50` or `cluster01` and the app automatically constructs the full `https://...:8080` path.
    - **Inventory**: Successful logins are automatically added to your local inventory for one-click access.
2. **Credentials**: 
    - Supports local cluster accounts and Active Directory.
    - **Formats**: `user`, `domain\user`, `user@domain.com`, or `user@sub.domain.com`.
3. **SSL**: Option to ignore SSL certificates for internal management networks.

---

## 🗺️ Navigation & Usage

The application is organized into 5 intuitive tabs:

### 1. 📈 Monitoring (Dashboard)
- View **Top Offenders** categorised by usage (Critical >90%, Warning >80%).
- Search and filter the full quota inventory.
- **Action**: Select a quota row to "focus" on it for the Universal Manager.

### 2. 🔧 Modify (Universal Object Manager)
- **Quota Settings**: An editable grid of every property returned by the API.
- **Snapshots**: View real-time snapshot data linked to the path.
- **Permissions**: Inspect the security descriptor (ACLs).
- **Decommission**: Securely delete the quota with a text-confirmation challenge.

### 3. ➕ Create (Provisioning)
- Form-based interface to create new Directory, User, Group, or Default quotas.

### 4. 📥 Export (Reporting)
- Generate full cluster reports filtered by Access Zone or Protocol.

### 5. 📜 Audit Log
- Review the **Daily Audit Log** specific to the current cluster.
- Logs are rotated daily (`hostname_MMDDYEAR.csv`) for compliance.

---

## 🛠️ Development

### Building the Bundle
If you modify any file in the `src/` directory, update the single-file distribution by running:
```bash
python3 bundle.py
```

---

## 📚 Technical Reference

- **Backend**: Uses the Dell PowerScale Platform API (PAPI) via the official `isilon-sdk`.
- **Target Version**: Optimized for **OneFS 9.12.0.1**.
- **Logs & Audit**: All logs are stored in `~/.papi-q/`.
    - `system.log`: Startup events, configuration errors, and API failures.
    - `[cluster]_[date].csv`: Compliance-ready audit trails for all quota changes.

---

## ⚖️ License & Support

Licensed under the MIT License. Maintained by [FranksOps](https://github.com/franksops).
