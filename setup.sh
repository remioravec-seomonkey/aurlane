#!/usr/bin/env bash
# Installe les dépendances du pipeline.
set -e
pip install -r requirements.txt
python3 -m playwright install chromium
echo
echo "Prêt. Enchaîner :"
echo "  python3 tools/explode.py capture.html --out site"
echo "  cp js/app.js site/js/app.js"
echo "  python3 tools/verify.py capture.html site/index.html"
