# Project Changes & Refinement Log

This file tracks improvements, bug fixes, and technical debt removal.

## [2026-04-27] Ultrathink Review & Production Hardening

### API & Backend (`src/api.py`, `src/audit.py`)
- **Distribution Safeguard**: Added `urlparse`, `glob`, and `datetime` to the `papi-q.py` header via `bundle.py`, resolving a potential runtime crash in the single-file distribution.
- **Robust Audit History**: Refined `read_audit_log` to safely handle corrupted or inaccessible CSV files during history aggregation.
- **Snapshot UX**: Integrated auto-sorting for snapshots (**Newest First**) to improve administrative visibility.
- **Hardened Quota Creation**: `create_quota` now skips zero/empty limits, preventing unintended "Unlimited" overwrites in OneFS.
- **Precision ACLs**: Added explicit `zone` support to `get_acl_for_path` to ensure correct permission retrieval across multiple Access Zones.
- **Response Robustness**: Implemented `getattr` safety checks in `_map_quota_response` to handle uninitialized PAPI objects without crashing.

### UI & technical Debt (`src/main.py`, `src/ui/session.py`, `src/ui/components.py`)
- **Name Derivation**: Implemented `urllib.parse` for cluster hostname derivation, with a multi-stage fallback to handle malformed IPs and URLs gracefully.
- **Encapsulation**: Replaced direct SDK calls in the UI with a refined `get_raw_quota` API wrapper, ensuring uniform error handling.
- **Pure Component Policy**: Logic for status badges and formatting is now strictly centralized in `utils.py`, with all redundant UI-layer formatters and unused functions fully purged.

### Verification
- **Test Alignment**: Updated unit tests to reflect refined 95/80/70 thresholds and multi-file history logic.
- **Bundle Sync**: Regenerated `papi-q.py` to include 100% of these refinements.
