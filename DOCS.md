# 📊 SmartQuota Manager: Documentation & Usage Guide

**SmartQuota Manager** is a high-performance, single-file management suite designed for Storage Administrators to monitor and manage Dell PowerScale (Isilon) clusters running **OneFS 9.12.0.1**.

## 🚀 Getting Started

### The Single-File Experience
The entire application is bundled into a single file: `papi-q.py`. 

### Running the App
```bash
python3 papi-q.py
```

### Universal Bootstrapper
The script includes an intelligent bootstrapper that detects your OS (**macOS or Linux**) and automatically handles environment setup:
*   **System Deps**: Detects and offers to install `brew` (macOS), `apt` (Debian/Ubuntu), or `dnf` (RHEL/CentOS) requirements.
*   **Python Deps**: Automatically installs `isilon-sdk`, `streamlit`, `pandas`, and `urllib3` via `pip`.
*   **Self-Launch**: Automatically invokes the Streamlit server after dependencies are met.

---

## 🔐 Authentication & Connectivity

### Login Format
*   **Active Directory Support**: Supports the `domain\user` format (use a single backslash in the UI).
*   **Saved Clusters**: Select from the 6 clusters pre-defined in `clusters.json`.
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

### 4. Audit Logging
*   Every modification, creation, or deletion is logged to a local `audit.csv`.
*   **Fields**: Timestamp, Admin User, Cluster, Action, Path, Old Limit, New Limit.

---

## 📚 Technical Reference & Source Links

### Backend: OneFS Platform API (PAPI)
The tool interacts with the OneFS PAPI on port 8080.
*   **API Docs**: [OneFS 9.12.0.1 PAPI Reference](https://www.dell.com/support/manuals/en-us/isilon-onefs/onefs-papi-9.12.0.1-ref/introduction)

### Libraries & SDKs
*   **Isilon SDK**: Official Dell Python client for OneFS.
    *   [Source (GitHub)](https://github.com/isilon/isilon_sdk) | [PyPI](https://pypi.org/project/isilon-sdk/)
*   **Streamlit**: The UI framework providing the web interface.
    *   [Documentation](https://docs.streamlit.io/)
*   **Pandas**: Used for high-speed quota filtering and CSV generation.
    *   [Documentation](https://pandas.pydata.org/docs/)

---

## 📁 File Structure
*   `papi-q.py`: The universal single-file distribution.
*   `clusters.json`: Your inventory of Isilon clusters.
*   `audit.csv`: Automatically generated log of administrator actions.
*   `src/`: Modular source code for development (contains `api.py`, `main.py`, etc.).
*   `bundle.py`: The build script used to regenerate `papi-q.py` after code changes.
