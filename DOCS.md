# 📊 SmartQuota Manager: Documentation & Usage Guide

**SmartQuota Manager** is a high-performance, single-file management suite designed for Storage Administrators to monitor and manage Dell PowerScale (Isilon) clusters running **OneFS 9.12.0.1**.

## 🚀 Getting Started

### The Single-File Experience
The entire application is bundled into a single file: `papi-q.py`. 

### Recommended "One-Liner" Deployment
Run this on any macOS or Linux jump box to download and launch the manager instantly:
```bash
curl -L -o papi-q.py https://raw.githubusercontent.com/franksops/papi-q/gemini/papi-q.py && python3 papi-q.py
```

### Universal Bootstrapper
The script includes an intelligent bootstrapper that handles environment setup:
*   **System Deps**: Detects and offers to install `brew` (macOS), `apt` (Debian/Ubuntu), or `dnf` (RHEL/CentOS) requirements.
*   **Python Deps**: Automatically installs `isilon-sdk`, `streamlit`, `pandas`, and `urllib3` via `pip`.
*   **Self-Launch**: Automatically invokes the Streamlit server after dependencies are met.

---

## 🔐 Authentication & Connectivity

### Login Format
*   **Active Directory Support**: Supports the `domain\user` format (use a single backslash in the UI).
*   **Auto-Saving Clusters**: Select from the saved clusters or enter a **Custom URL**. Successful custom logins are automatically added to your inventory for future use.
*   **Custom URL**: Select "Custom URL..." from the dropdown to manually enter a management IP or FQDN (e.g., `https://10.1.1.50:8080`).

### Security
*   **Zero Persistence**: Credentials are held in volatile memory and are never saved to disk.
*   **SSL Verification**: Option to ignore self-signed certificates (common in internal management networks).

---

## 🛠️ Core Features

### 1. Quota Lifecycle Management (CRUD)
*   **➕ Create**: Provision new Directory, User, Group, or Default quotas on any `/ifs` path.
*   **📈 Monitor**: Real-time dashboard showing Top Offenders (Critical/Warning/Notice) and a paginated searchable list of all quotas.
*   **🔧 Universal Update**: Use the **Dynamic Property Editor** to modify any field exposed by the OneFS API (not just limits).
*   **🗑️ Delete**: Safely decommission quotas with a "DELETE" text-confirmation challenge.

### 2. Universal Object Manager (Advanced View)
When you select a quota, the manager provides a 360-degree view of the filesystem path:
*   **⚙️ Dynamic Grid**: Edits limits, advisory thresholds, and flags like `include_snapshots`.
*   **📸 Snapshot Viewer**: Lists all snapshots currently associated with the path (ID, Name, Created Date, Size).
*   **🔒 Permissions (ACL)**: Inspects the filesystem security, showing the Owner, Group, and every Access Control Entry (ACE) on the path.

### 3. Bulk Exporting
*   **Multi-Scope**: Export all quotas, or filter by Access Zone or Protocol.
*   **Protocol Mapping**: Automatically tags quotas with "SMB" or "NFS" by cross-referencing share/export configurations.
*   **Excel Ready**: Generates a human-readable CSV file for reporting or offline analysis.

### 4. Audit Logging (Compliance Ready)
*   **Daily Rotation**: Logs are named `hostname_MMDDYEAR.csv` (e.g., `cluster01_04272026.csv`).
*   **Timestamped**: All entries use a human-readable `YYYY-MM-DD HH:MM:SS` format.
*   **Cluster Isolation**: Each Isilon cluster maintains its own independent, daily audit log.
*   **Persistent**: New logs are only created on a new day; otherwise, entries are appended.

---

## 📚 Technical Reference & Official Resources

### In-App Documentation
Every tab in the application includes direct links to the **Official Dell PowerScale OneFS 9.12.0.x Documentation**:
*   **Platform API Reference**: Direct links to Quota, Snapshot, and Namespace API documentation.
*   **CLI Reference**: Access to the full OneFS 9.12 CLI Command Reference (PDF).
*   **Info Hub**: Central landing page for all OneFS 9.12 manuals.

### Libraries & SDKs
*   **Isilon SDK**: Official Dell Python client for OneFS (`isilon_sdk.v9_12_0`).
*   **Streamlit**: High-performance UI framework.
*   **Pandas**: Data processing engine for reporting and analytics.

---

## 📁 File Structure
*   `papi-q.py`: The universal single-file distribution.
*   `bundle.py`: The build script used to regenerate `papi-q.py` from the `src/` modules.
*   `clusters.json`: Your dynamic inventory of Isilon clusters (located in `~/.papi-q/`).
*   `audit_*.csv`: Daily cluster-specific audit logs (located in `~/.papi-q/`).
*   `src/`: Modular source code for development.
