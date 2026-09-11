"""Downloads VDA5050 JSON schemas from the official GitHub repository.

Usage:
    python scripts/update_schemas.py [VERSION]

VERSION defaults to release/2.0.0
"""

import sys
import urllib.request
from pathlib import Path

VERSION = sys.argv[1] if len(sys.argv) > 1 else "release/2.0.0"
BASE_URL = f"https://raw.githubusercontent.com/VDA5050/VDA5050/{VERSION}/json_schemas"
SCHEMAS_DIR = Path(__file__).parent.parent / "src" / "rmf2_vda5050_master" / "schemas"

# Maps local filename -> upstream filename (some lack the .json extension)
SCHEMAS: dict[str, str] = {
    "connection.schema.json": "connection.schema.json",
    "instantActions.schema.json": "instantActions.schema.json",
    "state.schema.json": "state.schema.json",
    "order.schema.json": "order.schema",
    "factsheet.schema.json": "factsheet.schema",
    "visualization.schema.json": "visualization.schema",
}

SCHEMAS_DIR.mkdir(parents=True, exist_ok=True)

for dest, src in SCHEMAS.items():
    url = f"{BASE_URL}/{src}"
    out = SCHEMAS_DIR / dest
    print(f"Downloading {src} -> {dest}")
    urllib.request.urlretrieve(url, out)

print(f"Done. Schemas written to {SCHEMAS_DIR}")
