#!/bin/bash
# Make "shape" a command you can type from any folder: one link in ~/.local/bin that
# points at bin/shape in this folder. It can be run again at any time. Nothing is copied,
# so the command always runs this folder's code.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
BIN_DIR="$HOME/.local/bin"

mkdir -p "$BIN_DIR"
ln -sfn "$ROOT/bin/shape" "$BIN_DIR/shape"

if ! "$BIN_DIR/shape" --version >/dev/null; then
  echo "linked $BIN_DIR/shape, but running it failed; see the message above" >&2
  exit 1
fi

case ":$PATH:" in
  *":$BIN_DIR:"*)
    echo "Installed. Type: shape" ;;
  *)
    echo "Linked $BIN_DIR/shape, but $BIN_DIR is not on your PATH in this shell."
    echo "Add it once, then open a new terminal:"
    echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc" ;;
esac
