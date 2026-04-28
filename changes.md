# Project Changes & Refinement Log

This file tracks improvements, bug fixes, and technical debt removal.

## [2026-04-27] Code Review & Entropy Fight

### API & Backend (`src/api.py`)
- **Consolidated SDK Imports**: Removed redundant `import isi_sdk` calls inside multiple methods; moved to class-level or initialization.
- **Improved `update_quota_dynamic`**: Simplified the nested object mapping logic for better reliability.
- **Default Access Zones**: Refined fallback to `["System"]` instead of `["system", "local"]` to align with OneFS standards.
- **Error Handling**: Added more descriptive error messages for ACL and Snapshot retrieval failures.

### UI & UX (`src/main.py`, `src/ui/components.py`)
- **Consolidated Formatting**: Removed duplicate `format_bytes` and `status_badge` logic from UI components, moving them to centralized `src/utils.py`.
- **Custom URL Parsing**: Hardened the logic to derive cluster names from URLs to prevent crashes on malformed inputs.
- **Dynamic Grid Refinement**: Standardized the display of numeric fields in the property editor.
- **Audit Tab Optimization**: Newest entries now appear at the top by default for better visibility.

### Utilities (`src/utils.py`)
- **De-duplication**: Gathered all byte conversion and status logic from across the project into this single module.
- **Type Safety**: Ensured all `bytes_to_gb` calculations handle zero or null inputs gracefully.

### Distribution (`bundle.py`)
- **Optimized Regex**: Improved the import-stripping logic to ensure the bundled `papi-q.py` remains clean and valid.
- **Version Check**: Added explicit Python version check to the bootstrapper (requires 3.8+).
