# Project Changes & Refinement Log

This file tracks improvements, bug fixes, and technical debt removal.

## [2026-04-27] Deep-Dive Review & Logic Hardening

### API & Backend (`src/api.py`)
- **Consolidated Models**: Centralized SDK model loading in `__init__` via a `_models` dictionary, eliminating redundant imports and improving performance.
- **Expanded Creation**: `create_quota` now supports soft limits, advisory limits, enforced flags, and snapshot inclusion, providing full lifecycle management.
- **Dynamic Update Safety**: Improved `update_quota_dynamic` to handle nested `limits` objects and added float-to-int conversion for Streamlit numeric inputs.
- **Snapshot Reliability**: Added safety checks to `get_snapshots_for_path` to prevent crashes on null timestamp data.

### UI & UX (`src/main.py`, `src/ui/components.py`)
- **Technical Debt Removal**: Deleted 3 unused functions (`create_modification_form`, `create_quota_viewer`, `create_quota_table`) and 3 redundant formatters.
- **Robust URL Parsing**: Implemented `urllib.parse` for custom URL derivation, preventing crashes on malformed management IPs.
- **Audit Data Integrity**: Fixed a bug where `modify_tab` recorded 0 as the new limit; it now correctly extracts the updated value from the API payload.
- **Dashboard Optimization**: Integrated "Provision Quota" as a top-level tab and added "Select max 1" guidance for the Universal Manager.

### Auditing & Verification (`src/audit.py`, `tests/`)
- **History Globbing**: `read_audit_log` now globs all daily CSV files for a cluster, providing a complete searchable history rather than just today's entries.
- **Improved Testing**: Updated the unit test suite to verify 95/80/70 thresholds and multi-file history aggregation.

### Distribution (`bundle.py`)
- **Version Guard**: Added Python 3.8+ check to the universal bootstrapper.
- **Sync**: Regenerated `papi-q.py` to include 100% of these refinements.
