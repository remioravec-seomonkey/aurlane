#!/usr/bin/env python3
"""
merge.py — refusionne le projet éclaté en un seul fichier HTML.

    python3 tools/merge.py site/ [--standalone]

Sans option        : CSS et JS inlinés, images encore dans assets/  (~660 Ko)
Avec --standalone  : tout inliné, images et polices en base64       (~5,4 Mo)

À quoi ça sert : livrer la page à quelqu'un qui ne veut qu'un fichier, ou la
déposer sur un hébergement qui n'accepte pas de dossier.

À quoi ça NE sert PAS : travailler dessus. Un fichier de 660 Ko représente
environ 170 000 tokens ; aucune fenêtre de chat ne le tient, et un modèle
qui l'édite rend du tronqué. Pour modifier, on reste sur les trois fichiers
séparés et on laisse Claude Code lire ce dont il a besoin.
"""
from __future__ import annotations

import argparse
import base64
import mimetypes
import os
import re
import sys

MIME_FIX = {
    ".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf",
    ".otf": "font/otf", ".eot": "application/vnd.ms-fontobject",
    ".avif": "image/avif", ".webp": "image/webp", ".svg": "image/svg+xml",
}


def build(root: str, standalone: bool) -> tuple[str, int]:
    html = open(os.path.join(root, "index.html"), encoding="utf-8").read()
    css = open(os.path.join(root, "style.css"), encoding="utf-8").read()
    js = open(os.path.join(root, "js", "app.js"), encoding="utf-8").read()

    html = re.sub(r'<link[^>]*href="[^"]*style\.css"[^>]*>',
                  "<style>\n" + css + "\n</style>", html, count=1)
    html = re.sub(r'<script[^>]*src="js/app\.js"[^>]*>\s*</script>',
                  "<script>\n" + js + "\n</script>", html, count=1)

    if not standalone:
        return html, 0

    cache: dict[str, str] = {}

    def uri(rel: str):
        if rel in cache:
            return cache[rel]
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            return None
        ext = os.path.splitext(path)[1].lower()
        mime = MIME_FIX.get(ext) or mimetypes.guess_type(path)[0] \
            or "application/octet-stream"
        with open(path, "rb") as f:
            cache[rel] = f"data:{mime};base64," + base64.b64encode(f.read()).decode()
        return cache[rel]

    html = re.sub(r'(["\'])(assets/(?:img|fonts)/[^"\']+)\1',
                  lambda m: m.group(1) + (uri(m.group(2)) or m.group(2)) + m.group(1),
                  html)
    html = re.sub(r"\b(assets/(?:img|fonts)/[A-Za-z0-9]+\.[a-z0-9]+)\b",
                  lambda m: uri(m.group(1)) or m.group(0), html)
    return html, len(cache)


def main():
    ap = argparse.ArgumentParser(description="Fusionne le projet en un fichier.")
    ap.add_argument("root", help="dossier du projet (contient index.html)")
    ap.add_argument("--standalone", action="store_true",
                    help="inliner aussi les images et polices en base64")
    a = ap.parse_args()

    if not os.path.isfile(os.path.join(a.root, "index.html")):
        sys.exit(f"Pas de index.html dans {a.root}")

    html, n = build(a.root, a.standalone)
    name = "index-standalone.html" if a.standalone else "index-single.html"
    out = os.path.join(a.root, name)
    open(out, "w", encoding="utf-8").write(html)

    ko = len(html) / 1024
    print(f"\n  {out}   {ko:.0f} Ko" + (f"   ({n} assets inlinés)" if n else ""))
    print(f"  soit environ {int(len(html) / 4 / 1000)} 000 tokens — "
          "trop pour un chat, prévu pour la livraison.\n")


if __name__ == "__main__":
    main()
