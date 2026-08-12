from pathlib import Path
import argparse
import json
import sys

# Add project root (Geos-Worker) to Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.services.pagasa_pipeline import run_pagasa_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Hourly PAGASA scrape -> activate GEOs geofences")
    parser.add_argument("--dry-run", action="store_true", help="Print matches without writing to MongoDB")
    args = parser.parse_args()

    try:
        summary = run_pagasa_pipeline(dry_run=args.dry_run)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()