# SmartQuota Manager for Dell PowerScale

A Streamlit-based management tool for monitoring and modifying SmartQuotas across multiple Dell PowerScale (OneFS) clusters.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/streamlit-1.32+-orange.svg)](https://streamlit.io/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## Features

- **Multi-cluster support**: Manage 3-4+ clusters from a single interface
- **Quota monitoring**: Real-time usage percentages with visual status indicators
- **Quick search**: Find shares by name or access zone
- **Top offenders**: Highlight shares exceeding usage thresholds (>90%, >80%, >70%)
- **Audit logging**: All modifications logged to CSV for compliance
- **Simple workflow**: Login → Find share → Adjust quota → Done

## Installation

### Prerequisites

- **Python 3.8+** (required for `asyncio` and modern typing)
- **Dell PowerScale (OneFS) cluster** with PAPI enabled on port 8080
- **Active Directory or local cluster accounts** for authentication
- **Network access** to your PowerScale clusters

### Quick Setup (Recommended)

Run the automated setup script (works on macOS and Linux):

```bash
chmod +x setup.sh
./setup.sh
```

This script will:
- Check Python version (requires 3.8+)
- Create a virtual environment
- Install all dependencies

### Manual Setup

```bash
# Clone the repository
git clone https://github.com/franksops/papi-q.git
cd papi-q

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### Dependencies

| Package | Version | Purpose |
|---------|---------|----------|
| isilon-sdk | 0.7.0 | Dell PowerScale OneFS API client |
| streamlit | >=1.32.0 | Web interface framework |
| pandas | >=2.0.0 | Data manipulation and display |
| urllib3 | >=2.0.0 | HTTP client for API communication |
| python-dotenv | >=1.0.0 | Environment variable management |

---

## Configuration

The application creates a `~/.papi-q/` directory on first run with configuration files.

### Configuration Files

#### clusters.json

Cluster definitions (API endpoints). This file is **required** before you can connect.

**Default location**: `~/.papi-q/clusters.json`

**Format**:
```json
{
  "cluster_name": "https://cluster-fqdn.local:8080",
  "cluster_prod": "https://isilon-prod.example.com:8080",
  "cluster_dr": "https://isilon-dr.example.com:8080"
}
```

**How to add clusters**:

1. **Via UI**: Click "Cluster Management" in the sidebar → Add each cluster
2. **Direct edit**: Edit `~/.papi-q/clusters.json` (restart app after changes)
3. **Bulk setup**: Pre-populate before first run for team deployment

#### config.json

Global application settings with defaults shown:

**Default location**: `~/.papi-q/config.json`

```json
{
  "verify_ssl": false,
  "log_file": "/home/username/isilon_admin_audit.csv",
  "max_retries": 3,
  "cache_ttl_seconds": 60
}
```

**Configuration Options**:

| Option | Default | Description |
|--------|---------|-------------|
| `verify_ssl` | `false` | Set `true` to enforce SSL certificate validation |
| `log_file` | `~/isilon_admin_audit.csv` | Full path to audit log CSV file |
| `max_retries` | `3` | Number of retry attempts for failed API calls |
| `cache_ttl_seconds` | `60` | Cache expiration time for quota data |

#### Audit Log

**Default location**: `~/isilon_admin_audit.csv`

All quota modifications are logged with:
- Timestamp
- Admin user
- Cluster name
- Action performed
- Share Name
- Path
- Old limit (GB)
- New limit (GB)

**Sample audit entry**:
```csv
timestamp,admin,cluster,action,share_name,path,old_limit_gb,new_limit_gb
2024-04-08 14:30:22,jsmith,cluster_prod,QUOTA_MODIFY,data_backup,/ifs/data/backup,500,750
```

---

## Usage

```bash
# Default (binds to 127.0.0.1 for security)
streamlit run src/main.py

# On dev machine (binds to specific IP for lan access)
streamlit run src/main.py --server.address 192.168.1.10

# With custom port
streamlit run src/main.py --server.port 8502
```

Then open the URL shown in your browser (default: http://127.0.0.1:8501)

### Streamlit Configuration

Streamlit settings are in `.streamlit/config.toml`:

| Setting | Default | Description |
|---------|---------|-------------|
| `server.address` | `127.0.0.1` | Bind address for the app |
| `server.headless` | `true` | Run without browser auto-open |
| `server.enableCORS` | `false` | Disable CORS for local use |
| `browser.gatherUsageStats` | `false` | Opt out of analytics |

---

## Workflow

1. **Connect**: Select cluster from dropdown, enter credentials
2. **Monitor**: View top offenders list on first load
3. **Search**: Filter by share name (partial match) or access zone
4. **Modify**: Select quota, enter new limits, confirm
5. **Verify**: Check audit log for recorded changes

###典型使用场景

#### scenario: Responsive Quota Adjustment

**Alert**: "Share `data_backup` at 96% usage"

1. Login to `cluster_prod`
2. Search for `data_backup`
3. Click quota in table
4. Modify from 500 GB → 750 GB
5. Confirm
6. Check audit log for verification

---

## Color Palette

- **Primary Orange**: Pantone 158 (#F58513)
- **Primary Green**: Pantone 3435 (#006837)
- **Background**: White

### Status Indicators

| Status | Color | Usage Threshold |
|--------|-------|-----------------|
| Critical | 🔴 Red (#D72638) | >90% |
| Warning | 🟡 Orange (#F58513) | 80-90% |
| Healthy | 🟢 Green (#006837) | <80% |

---

## Requirements

- Python 3.8+
- OneFS SDK 0.7.0
- Streamlit 1.32+
- Access to Dell PowerScale cluster(s)

---

## Development

### Project Structure

```
papi-q/
├── src/
│   ├── __init__.py
│   ├── api.py          # OneFS PAPI client wrapper
│   ├── audit.py        # Audit logging functionality
│   ├── config.py       # Configuration management
│   ├── main.py         # Streamlit entry point
│   ├── ui/             # UI components
│   │   ├── components.py
│   │   └── session.py
│   └── utils.py        # Utility functions
├── tests/              # Unit tests
├── docs/               # Documentation
│   ├── API.md
│   ├── QUICKSTART.md
│   └── REVIEW.md
├── assets/             # Images and resources
├── setup.sh            # Automated setup script
├── requirements.txt    # Python dependencies
└── README.md
```

### Running Tests

```bash
source venv/bin/activate
pytest tests/ -v
```

### Building Documentation

```bash
pip install mkdocs
mkdocs serve
```

---

## Contributing

Contributions are welcome! Please read our contributing guidelines before submitting pull requests.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- [Dell PowerScale OneFS SDK](https://github.com/dell/isilon-sdk-python)
- [Streamlit](https://streamlit.io/)

---

## Support

For issues and feature requests, please file an issue on GitHub.
