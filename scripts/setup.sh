#!/bin/sh
set -eu

repository_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repository_dir"

if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created local .env from .env.example."
fi
chmod 600 .env

(cd backend && uv run python - <<'PY'
from pathlib import Path

from cryptography.fernet import Fernet

repository = Path.cwd().parent
environment_path = repository / ".env"
example_path = repository / ".env.example"
content = environment_path.read_text(encoding="utf-8")
example = example_path.read_text(encoding="utf-8")


def assignment(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    name, value = stripped.split("=", 1)
    if not name.replace("_", "").isalnum():
        return None
    return name, value


configured_names = {
    parsed[0]
    for line in content.splitlines()
    if (parsed := assignment(line)) is not None
}
missing_defaults = [
    line
    for line in example.splitlines()
    if (parsed := assignment(line)) is not None
    and parsed[0] not in configured_names
]
if missing_defaults:
    content = content.rstrip("\n")
    if content:
        content += "\n"
    content += "\n".join(missing_defaults) + "\n"

secret_names = {
    "SESSION_ENCRYPTION_KEY",
    "PII_ENCRYPTION_KEY",
    "INTEGRATION_ENCRYPTION_KEY",
}
updated_lines: list[str] = []
for line in content.splitlines():
    parsed = assignment(line)
    if parsed is not None and parsed[0] in secret_names and not parsed[1]:
        updated_lines.append(f"{parsed[0]}={Fernet.generate_key().decode('ascii')}")
    else:
        updated_lines.append(line)

environment_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
PY
)
echo "Verified local environment defaults and generated any missing encryption keys."

uv sync --project backend --all-groups --frozen
(cd frontend && npm ci)
docker compose build

echo "Setup complete. Run 'make run' to start OwnSIS."
