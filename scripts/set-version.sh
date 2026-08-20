#!/usr/bin/env bash
set -euo pipefail

version=${1:?version required}
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
target="${root}/version.py"
citation="${root}/CITATION.cff"

if ! grep -q '^VERSION = "' "$target"; then
  printf 'no VERSION assignment found in %s\n' "$target" >&2
  exit 1
fi

if ! grep -q '^version: ' "$citation"; then
  printf 'no version found in %s\n' "$citation" >&2
  exit 1
fi

tmp=$(mktemp "${TMPDIR:-/tmp}/sf-version-XXXXXX")
sed "s/^VERSION = \".*\"$/VERSION = \"${version}\"/" "$target" >"$tmp"
mv -f "$tmp" "$target"

tmp=$(mktemp "${TMPDIR:-/tmp}/sf-citation-XXXXXX")
sed "s/^version: .*$/version: ${version}/" "$citation" >"$tmp"
mv -f "$tmp" "$citation"

printf 'version set to %s\n' "$(python3 -c 'import version; print(version.VERSION)' 2>/dev/null || grep '^VERSION' "$target")"
