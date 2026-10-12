#!/bin/zsh
set -euo pipefail
ROOT=${0:A:h:h}
OUTPUT=${1:-$ROOT:h/work/cardme-control-plane.zip}
STAGE=$(mktemp -d "${TMPDIR:-/tmp}/cardme-control-plane.XXXXXX")
trap 'rm -rf "$STAGE"' EXIT
cd "$ROOT"
npm run build
cp package.json package-lock.json host.json "$STAGE/"
cp -R dist "$STAGE/"
npm ci --omit=dev --ignore-scripts --prefix "$STAGE"
mkdir -p "${OUTPUT:h}"
(cd "$STAGE" && zip -qr "$OUTPUT" .)
print -r -- "$OUTPUT"
