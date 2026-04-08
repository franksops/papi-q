# SmartQuota Manager for Dell PowerScale

A Streamlit-based management tool for monitoring and modifying SmartQuotas across multiple Dell PowerScale (OneFS) clusters.

## Features

- **Multi-cluster support**: Manage 3-4+ clusters from a single interface
- **Quota monitoring**: Real-time usage percentages with visual status indicators
- **Quick search**: Find shares by name or access zone
- **Top offenders**: Highlight shares exceeding usage thresholds (>90%, >80%, >70%)
- **Audit logging**: All modifications logged to CSV for compliance
- **Simple workflow**: Login → Find share → Adjust quota → Done

## Installation

```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration

The tool creates a `~/.papi-q/` directory on first run with:

- `clusters.json`: Your cluster definitions
- `config.json`: Global settings (SSL, log file path)

### clusters.json

```json
{
  "cluster1-name": "https://cluster1.fqdn.local:8080",
  "cluster2-name": "https://cluster2.fqdn.local:8080"
}
```

## Usage

```bash
streamlit run src/main.py
```

Then open http://localhost:8501 in your browser.

## Workflow

1. **Connect**: Select cluster from dropdown, enter credentials
2. **Monitor**: View top offenders list on first load
3. **Search**: Filter by share name (partial match) or access zone
4. **Modify**: Select quota, enter new limits, confirm
5. **Verify**: Check audit log for recorded changes

## Color Palette

- **Primary Orange**: Pantone 158 (#F58513)
- **Primary Green**: Pantone 3435 (#006837)
- **Background**: White

## Requirements

- Python 3.8+
- OneFS SDK 0.7.0
- Streamlit 1.32+
