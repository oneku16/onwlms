"""Export or verify the deterministic API contract used by the frontend."""

import argparse
import json
import sys
from base64 import urlsafe_b64encode
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SOURCE = REPOSITORY_ROOT / "backend" / "src"
OUTPUT_PATH = REPOSITORY_ROOT / "backend" / "openapi.json"
# Schema construction encrypts no data; this known test key only satisfies factories.
CONTRACT_KEY = urlsafe_b64encode(bytes(32)).decode("ascii")


def _contract_bytes() -> bytes:
    """Build the schema with explicit settings and stable JSON serialization."""

    sys.path.insert(0, str(BACKEND_SOURCE))

    from composition import create_application
    from core.settings import AppEnvironment
    from core.settings import Settings

    settings = Settings(
        APP_ENV=AppEnvironment.TEST,
        OPENAPI_ENABLED=True,
        DEV_AUTH_ENABLED=True,
        MCP_ENABLED=False,
        SESSION_ENCRYPTION_KEY=CONTRACT_KEY,
        PII_ENCRYPTION_KEY=CONTRACT_KEY,
        INTEGRATION_ENCRYPTION_KEY=CONTRACT_KEY,
        OWNID_ISSUER="",
        OWNID_CLIENT_ID="",
        OWNID_CLIENT_SECRET="",
    )
    schema = create_application(settings=settings).openapi()
    return (json.dumps(schema, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when the checked-in OpenAPI document differs",
    )
    return parser.parse_args()


def main() -> None:
    """Write the schema, or fail without changing it when checking drift."""

    arguments = _parse_arguments()
    expected = _contract_bytes()
    if arguments.check:
        actual = OUTPUT_PATH.read_bytes() if OUTPUT_PATH.exists() else None
        if actual != expected:
            message = "backend/openapi.json is stale; run `make openapi`"
            raise SystemExit(message)
        return
    OUTPUT_PATH.write_bytes(expected)


if __name__ == "__main__":
    main()
