#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
tool_directory="$repository_root/tools/openapi-contract"
input_path="$repository_root/backend/openapi.json"
output_path="$repository_root/frontend/lib/api/generated/openapi.ts"
output_directory=$(dirname -- "$output_path")
check=false

if [ "${1:-}" = "--check" ]; then
    check=true
    shift
fi
if [ "$#" -ne 0 ]; then
    echo "usage: $0 [--check]" >&2
    exit 2
fi
if [ ! -f "$input_path" ]; then
    echo "backend/openapi.json is missing; run 'make openapi'" >&2
    exit 1
fi

npm --prefix "$tool_directory" ci --ignore-scripts --no-audit --no-fund

temporary_directory=$(mktemp -d "$output_directory/openapi.XXXXXX")
temporary_path="$temporary_directory/openapi.ts"
cleanup() {
    rm -f "$temporary_path"
    rmdir "$temporary_directory"
}
trap cleanup EXIT HUP INT TERM

"$tool_directory/node_modules/.bin/openapi-typescript" \
    "$input_path" \
    --alphabetize \
    --immutable \
    --output "$temporary_path"
"$tool_directory/node_modules/.bin/prettier" \
    --write \
    --parser typescript \
    "$temporary_path" >/dev/null

if [ "$check" = true ]; then
    if [ ! -f "$output_path" ] || ! cmp -s "$temporary_path" "$output_path"; then
        if [ -f "$output_path" ]; then
            diff -u "$output_path" "$temporary_path" || true
        fi
        echo "frontend OpenAPI types are stale; run 'make openapi'" >&2
        exit 1
    fi
    exit 0
fi

mv "$temporary_path" "$output_path"
chmod 0644 "$output_path"
rmdir "$temporary_directory"
trap - EXIT HUP INT TERM
