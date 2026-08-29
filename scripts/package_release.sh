#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(PYTHONPATH="$PROJECT_DIR" python3 -c 'from televault import __version__; print(__version__)')"
OUTPUT_DIR="${1:-$PROJECT_DIR/release}"
STAGE_DIR="$(mktemp -d)"
PACKAGE_DIR="$STAGE_DIR/TeleVault-$VERSION"

cleanup() { rm -rf -- "$STAGE_DIR"; }
trap cleanup EXIT

mkdir -p "$PACKAGE_DIR" "$OUTPUT_DIR"
files=(
  televault pytests scripts .github
  install.sh start.sh requirements.txt requirements-dev.txt pyproject.toml
  Dockerfile docker-compose.yml .dockerignore .gitignore
  README.md SECURITY.md LICENSE
)
for item in "${files[@]}"; do
  cp -a "$PROJECT_DIR/$item" "$PACKAGE_DIR/"
done
find "$PACKAGE_DIR" -type d -name __pycache__ -prune -exec rm -rf -- {} +
find "$PACKAGE_DIR" -type f -name '*.pyc' -delete
chmod +x "$PACKAGE_DIR/install.sh" "$PACKAGE_DIR/start.sh" "$PACKAGE_DIR/scripts/televaultctl" "$PACKAGE_DIR/scripts/package_release.sh"

(cd "$STAGE_DIR" && zip -q -r "$OUTPUT_DIR/TeleVault-$VERSION.zip" "TeleVault-$VERSION")
sha256sum "$OUTPUT_DIR/TeleVault-$VERSION.zip" > "$OUTPUT_DIR/TeleVault-$VERSION.zip.sha256"
printf '%s\n' "$OUTPUT_DIR/TeleVault-$VERSION.zip"

