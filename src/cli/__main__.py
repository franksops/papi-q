"""Command-line interface functions for SmartQuota Manager."""

import sys
import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="SmartQuota Manager for Dell PowerScale",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  papi-q --clusters        Show configured clusters
  papi-q --add_cluster     Interactive addition of cluster
  papi-q run               Start Streamlit app
        """,
    )
    
    parser.add_argument(
        "--clusters",
        action="store_true",
        help="List configured clusters",
    )
    
    parser.add_argument(
        "--add-cluster",
        action="store_true",
        help="Add a new cluster interactively",
    )
    
    parser.add_argument(
        "command",
        nargs="?",
        choices=["run"],
        default="run",
        help="Command to execute (default: run)",
    )
    
    return parser.parse_args()


def main() -> int:
    """Main CLI entry point."""
    args = parse_args()
    
    if args.clusters:
        from src.config import load_clusters
        clusters = load_clusters()
        if not clusters:
            print("No clusters configured. Edit ~/.papi-q/clusters.json")
            return 1
        print("\nConfigured Clusters:")
        for name, url in clusters.items():
            print(f"  {name}: {url}")
        return 0
    
    if args.add_cluster:
        from src.config import add_cluster, save_clusters, load_clusters
        name = input("Enter cluster name (short, memorable): ").strip()
        url = input("Enter cluster API URL (e.g., https://cluster.fqdn:8080): ").strip()
        
        if not name or not url:
            print("Error: Name and URL are required.")
            return 1
        
        url = url.rstrip("/") + ":8080" if not url.endswith(":8080") else url
        
        if not url.startswith("https://"):
            print("Warning: Using HTTP instead of HTTPS (SSL may fail)")
        
        add_cluster(name, url)
        print(f"Added cluster: {name} -> {url}")
        return 0
    
    if args.command == "run":
        import subprocess
        subprocess.run([sys.executable, "-m", "streamlit", "run", "src/main.py"])
        return 0
    
    return 1


if __name__ == "__main__":
    sys.exit(main())
