#!/usr/bin/env bash
# Assemble the static web version into _site/ (what GitHub Pages serves).
#   scripts/build-web.sh           build only
#   scripts/build-web.sh --serve   build, then serve on http://localhost:8000
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf _site
mkdir -p _site
cp web/index.html web/style.css web/app.js web/engine.js _site/
cp src/content/content.json _site/
echo "built _site/ ($(ls _site | wc -l) files)"
if [[ "${1:-}" == "--serve" ]]; then
  echo "serving on http://localhost:8000 (Ctrl-C to stop)"
  python3 -m http.server 8000 --directory _site
fi
