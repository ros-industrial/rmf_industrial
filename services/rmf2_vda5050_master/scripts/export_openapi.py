"""Export the OpenAPI schema to a JSON file without starting the server."""

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output-dir",
        default=".",
        help="Directory to write openapi.json into (default: current directory)",
    )
    args = parser.parse_args()

    from rmf2_vda5050_master.app import app

    output = Path(args.output_dir) / "openapi.json"
    output.write_text(json.dumps(app.openapi(), indent=2))
    print(f"OpenAPI schema written to {output}")


if __name__ == "__main__":
    main()
