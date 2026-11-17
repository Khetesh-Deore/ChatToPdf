#!/usr/bin/env bash
# Copies KaTeX into app/vendor/katex so PDF rendering never needs the internet.
# Requires Node/npm once; after that everything is offline.
set -euo pipefail

V=0.16.11
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"

( cd "$TMP" && npm pack "katex@$V" --silent && tar xzf "katex-$V.tgz" )

DEST="$ROOT/app/vendor/katex"
mkdir -p "$DEST"
cp "$TMP/package/dist/katex.min.css" \
   "$TMP/package/dist/katex.min.js" \
   "$DEST/"
cp "$TMP/package/dist/contrib/auto-render.min.js" "$DEST/"
cp -r "$TMP/package/dist/fonts" "$DEST/"

rm -rf "$TMP"
echo "KaTeX $V vendored into $DEST"
