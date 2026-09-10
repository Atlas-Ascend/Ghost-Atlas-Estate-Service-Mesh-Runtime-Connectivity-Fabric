#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
ROOT="${1:-$PWD}"
SRC="$ROOT/global-resolution/cognitive-office-mesh"
DEST="$HOME/.config/ghost-atlas/cognitive-office-mesh"
mkdir -p "$DEST" "$PREFIX/bin"
cp "$SRC/bundles.yaml" "$DEST/bundles.yaml"
cp "$SRC/mesh.yaml" "$DEST/mesh.yaml"
cp "$SRC/closed-loop.yaml" "$DEST/closed-loop.yaml"
cp "$SRC/invocation-envelope.yaml" "$DEST/invocation-envelope.yaml"
cp "$SRC/termux/ga-office" "$PREFIX/bin/ga-office"
chmod 700 "$PREFIX/bin/ga-office"
printf 'GA_OFFICE_MESH=INSTALLED\nREGISTRY=%s\nCLI=%s\n' "$DEST/bundles.yaml" "$PREFIX/bin/ga-office"
