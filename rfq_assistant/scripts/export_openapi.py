"""Export the backend OpenAPI schema for frontend type generation.

Usage (from the repository root, with backend dependencies installed):

    python -m rfq_assistant.scripts.export_openapi
    cd frontend && npm run gen:types

The checked-in ``frontend/openapi.json`` is verified against the live FastAPI
app by ``tests/test_openapi_contract.py`` so drift fails CI.
"""

import argparse
import json
from pathlib import Path

from rfq_assistant.api.app import app

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "frontend" / "openapi.json"


def render_schema() -> str:
    """Return a deterministic JSON representation of the live API schema."""
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the checked-in schema is stale.",
    )
    args = parser.parse_args()

    rendered = render_schema()
    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        if current != rendered:
            raise SystemExit(
                f"OpenAPI schema is stale: {args.output}. "
                "Run `python -m rfq_assistant.scripts.export_openapi` and commit the result."
            )
        print(f"OpenAPI schema is up to date: {args.output}")
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
