# 📊 SmartQuota Manager: Project Intelligence & Mandates

## 🎯 Project Overview
SmartQuota Manager is a specialized administrative tool for Dell PowerScale (Isilon) OneFS 9.12.0.1. It provides a Streamlit-based interface for Quota Lifecycle Management, Snapshot inspection, and ACL auditing.

### 🏛️ Core Architecture
- **Source-to-Bundle Workflow**: Development occurs in the `src/` directory. Production distribution is a single-file bootstrapper (`papi-q.py`).
- **Backend**: Dell PowerScale Platform API (PAPI) via the official `isilon-sdk`.
- **Frontend**: Streamlit-based SPA (Single Page Application).
- **State**: Volatile session management via `streamlit.session_state`.
- **Persistence**: Local configuration and audit logs stored in `~/.papi-q/`.

---

## 🛠️ Development Mandates

### 1. Single-File Distribution (Crucial)
- **NEVER** modify `papi-q.py` directly. It is a generated file.
- **Workflow**: Edit files in `src/` -> Run `python3 bundle.py` to regenerate the bundle.
- Any change to core logic or UI must be reflected in the modular `src/` structure.

### 2. Audit & Compliance
- **MANDATORY**: Every mutating action (**CREATE**, **UPDATE**, **DELETE**) MUST trigger a call to `src.audit.write_audit_entry`.
- Audit logs are cluster-specific and rotated daily (`hostname_MMDDYEAR.csv`).
- Logs must capture: `admin`, `cluster`, `action`, `share_name`, `path`, `old_limit_gb`, `new_limit_gb`.

### 3. API & Data Handling
- Use the `IsilonAPI` wrapper in `src/api.py` for all cluster interactions.
- **Typing**: Use the `QuotaEntry` dataclass for quota objects.
- **Units**: All storage values should be processed in bytes internally and converted to GB/TB for UI display using `src.utils`.
- **Security**: Credentials must never be persisted. Only store the API client in `session_state`.

### 4. UI/UX Conventions
- **Theming**: Adhere to the defined Green/Orange color palette (`--p-green: #006837`, `--p-orange: #F58513`).
- **Components**: Reusable UI logic (Grid, Snapshot Viewer, ACL Viewer) belongs in `src/ui/components.py`.
- **Badges**: Use `src.utils.status_badge` for health indicators (🔴 Critical > 95%, 🟡 Warning > 80%).

### 5. Error Management
- Wrap API calls with `src.ui.session.handle_api_error` to ensure consistent UI feedback and session cleanup on authentication failures.

---

## 📂 Key File Map
| Path | Purpose |
| :--- | :--- |
| `src/main.py` | Main Streamlit entry point. |
| `src/constants.py` | Shared constants and path definitions. |
| `src/logger.py` | System-level logging (startup/errors). |
| `src/api.py` | Isilon SDK wrapper & PAPI logic. |
| `src/audit.py` | Compliance logging & log rotation. |
| `src/ui/` | UI components and session state management. |
| `bundle.py` | Build script for single-file distribution. |
| `tests/` | Unit tests for API, Audit, and Utils. |

---

## 🧪 Testing Protocol
- Run tests using `pytest` from the root directory.
- New features in `src/api.py` or `src/utils.py` require corresponding test updates in `tests/`.
- Ensure `isilon-sdk` is installed in the test environment.
