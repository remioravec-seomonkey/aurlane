#!/usr/bin/env python3
"""
explode.py — éclate une capture SingleFile en projet HTML / CSS / JS travaillable.

    python3 tools/explode.py capture.html --out site/ [--keep-third-party]

Ce que fait le script :
  1. extrait chaque data:URI (images, polices) en fichier réel dans assets/
  2. concatène tous les blocs <style> dans style.css, en respectant l'ordre
     du DOM et en réencapsulant les blocs porteurs d'un attribut media
  3. réécrit les références (src, href, srcset, style="", data-imgurl…)
  4. retire les artefacts de capture : meta CSP, commentaires
  5. retire les résidus tiers figés dans le DOM (bandeau cookies, iframes
     vides, liens WordPress morts) — désactivable avec --keep-third-party
  6. écrit index.html + style.css et branche js/app.js

Pièges gérés (ne pas « corriger » sans lire) :
  - SingleFile injecte <meta http-equiv="Content-Security-Policy"> qui bloque
    tout CSS et JS externe. Sans suppression, la page reste nue.
  - SingleFile déclare les images de fond dans des variables CSS
    (--sf-img-42: url(...)). Les URL relatives d'une custom property sont
    résolues par le navigateur contre le DOCUMENT, pas contre la feuille de
    style. style.css doit donc rester à la RACINE, à côté de index.html, et
    les chemins d'assets ne portent aucun ../ — sinon les images de fond
    partent chercher un dossier au-dessus du projet.
  - SingleFile marque .sf-hidden tout élément non affiché à l'instant de la
    capture, et injecte .sf-hidden{display:none!important}. Ces éléments sont
    donc invisibles SANS être supprimés : les jeter ne gagne pas un pixel et
    emporte des noeuds dont le comportement dépend (bouton burger masqué au
    desktop, images d'un mega-menu affichées au survol, panneau de résultats
    de recherche). On les CONSERVE, et c'est à app.js de retirer la classe
    sur les seuls éléments qu'il réanime.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import os
import re
import sys

try:
    from bs4 import BeautifulSoup, Comment
except ImportError:
    sys.exit("Il manque beautifulsoup4 : pip install beautifulsoup4 lxml")

EXT = {
    "image/svg+xml": "svg", "image/webp": "webp", "image/png": "png",
    "image/jpeg": "jpg", "image/jpg": "jpg", "image/avif": "avif",
    "image/gif": "gif", "image/x-icon": "ico",
    "image/vnd.microsoft.icon": "ico", "image/bmp": "bmp",
    "font/woff2": "woff2", "font/woff": "woff", "font/ttf": "ttf",
    "font/otf": "otf", "font/opentype": "otf", "font/sfnt": "ttf",
    "application/font-woff2": "woff2", "application/font-woff": "woff",
    "application/x-font-woff": "woff", "application/x-font-ttf": "ttf",
    "application/x-font-truetype": "ttf", "application/x-font-opentype": "otf",
    "application/vnd.ms-fontobject": "eot",
}

FONT_EXT = {"woff", "woff2", "ttf", "otf", "eot"}

DATA_RE = re.compile(
    r"data:([a-zA-Z0-9.+/-]+);base64,([A-Za-z0-9+/=\s]+?)(?=[\"')\s,]|$)"
)

# attributs susceptibles de contenir une URL d'asset
URL_ATTRS = ("src", "href", "srcset", "poster", "content", "data-imgurl",
             "data-src", "data-srcset", "data-bg", "xlink:href")

DEAD_WP = ("/feed/", "wp-json", "xmlrpc.php")


class Extractor:
    def __init__(self, out: str):
        self.out = out
        self.seen: dict[str, str] = {}
        self.n_img = 0
        self.n_font = 0
        self.n_svg_inline = 0
        self.bytes = 0
        for d in ("", "js", "assets/img", "assets/fonts", "tools"):
            os.makedirs(os.path.join(out, d), exist_ok=True)

    def dump(self, mime: str, b64: str) -> str | None:
        """Écrit un data:URI sur disque, dédupliqué, et renvoie son chemin."""
        clean = re.sub(r"\s", "", b64)
        key = hashlib.sha1(clean[:6000].encode()).hexdigest()[:12]
        if key in self.seen:
            return self.seen[key]

        ext = EXT.get(mime.lower(), "bin")
        folder = "fonts" if (ext in FONT_EXT or "font" in mime.lower()) else "img"
        try:
            data = base64.b64decode(clean + "===")
        except Exception:
            return None
        if len(data) < 40:          # pixel espion, gif transparent : on laisse inline
            return None

        rel = f"assets/{folder}/{key}.{ext}"
        with open(os.path.join(self.out, rel), "wb") as f:
            f.write(data)

        if folder == "fonts":
            self.n_font += 1
        else:
            self.n_img += 1
        self.bytes += len(data)
        self.seen[key] = rel
        return rel

    def rewrite(self, text: str, keep_svg: bool = False) -> str:
        """Remplace les data:URI par des chemins de fichiers.

        keep_svg laisse les SVG inline : à utiliser pour tout ce qui est du CSS.
        Un SVG servi par mask-image ou filter: url() est soumis au CORS, et
        deux fichiers file:// sont cross-origin pour Chromium — extrait, le
        masque est bloqué et l'icône disparaît. Inline, il marche partout, et
        ces SVG-là pèsent quelques centaines d'octets.
        """
        def sub(m):
            if keep_svg and m.group(1).lower() == "image/svg+xml":
                self.n_svg_inline += 1
                return m.group(0)
            rel = self.dump(m.group(1), m.group(2))
            return rel if rel else m.group(0)
        return DATA_RE.sub(sub, text)


def run(src: str, out: str, keep_third_party: bool = False) -> dict:
    raw = open(src, encoding="utf-8", errors="replace").read()
    ex = Extractor(out)
    soup = BeautifulSoup(raw, "lxml")

    # ---------------------------------------------------------------- CSS
    parts, n_blocks = [], 0
    for tag in list(soup.find_all("style")):
        body = tag.string or tag.get_text() or ""
        if not body.strip():
            tag.decompose()
            continue
        media = tag.get("media")
        body = ex.rewrite(body, keep_svg=True)
        if media and media.strip().lower() not in ("all", "screen"):
            body = f"@media {media} {{\n{body}\n}}"
        parts.append(f"\n/* ===== bloc {n_blocks:02d}"
                     + (f" | media={media}" if media else "")
                     + " ===== */\n" + body)
        n_blocks += 1
        tag.decompose()

    css = "".join(parts)
    with open(os.path.join(out, "style.css"), "w", encoding="utf-8") as f:
        f.write(css)

    # ----------------------------------------------- attributs et styles inline
    for tag in soup.find_all(style=True):
        if "data:" in tag["style"]:
            tag["style"] = ex.rewrite(tag["style"], keep_svg=True)

    for attr in URL_ATTRS:
        for tag in soup.find_all(attrs={attr: True}):
            v = tag.get(attr)
            if isinstance(v, str) and "data:" in v:
                tag[attr] = ex.rewrite(v)

    # ---------------------------------------------------- artefacts de capture
    n_hidden = len(soup.select(".sf-hidden"))   # conservés, voir l'en-tête
    for tag in list(soup.find_all("script")):
        tag.decompose()
    for c in soup.find_all(string=lambda t: isinstance(t, Comment)):
        low = str(c).lower()
        if "singlefile" in low or "r-content" in low:
            c.extract()

    removed = {}

    def note(k):
        removed[k] = removed.get(k, 0) + 1

    if not keep_third_party:
        for sel in ("#axeptio_overlay", ".axeptio_mount", "#tarteaucitron",
                    "#onetrust-consent-sdk", ".cky-consent-container",
                    "#didomi-host", ".cmplz-cookiebanner", "#cmplz-cookiebanner-container",
                    ".a11y-speak-region", ".a11y-speak-intro-text"):
            for el in soup.select(sel):
                note(sel)
                el.decompose()
        for fr in list(soup.find_all("iframe")):
            if not fr.get("src"):
                note("iframe vide")
                fr.decompose()
        if soup.head:
            for l in list(soup.head.find_all("link")):
                rel = " ".join(l.get("rel") or [])
                href = l.get("href") or ""
                if any(k in href for k in DEAD_WP) or rel in ("EditURI", "shortlink") \
                   or rel.startswith("https://api.w.org"):
                    note("link mort")
                    l.decompose()
        for f in soup.find_all("form"):
            if f.get("action"):
                f["data-original-action"] = f["action"]
                f["action"] = "#"
                note("form neutralisé")

    # -------------------------------------------------------------- branchement
    if soup.head:
        link = soup.new_tag("link", rel="stylesheet", href="style.css")
        soup.head.append(link)
    if soup.body:
        s = soup.new_tag("script", src="js/app.js")
        s["defer"] = ""
        soup.body.append(s)

    html = soup.prettify(formatter="html5")
    # la CSP de SingleFile bloquerait style.css et app.js
    html, n_csp = re.subn(
        r'<meta[^>]*http-equiv="Content-Security-Policy"[^>]*>\s*', "", html, flags=re.I
    )

    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    return {
        "html_ko": len(html) / 1024,
        "css_ko": len(css) / 1024,
        "css_blocks": n_blocks,
        "images": ex.n_img,
        "fonts": ex.n_font,
        "assets_mo": ex.bytes / 1024 / 1024,
        "csp_removed": n_csp,
        "svg_inline": ex.n_svg_inline,
        "hidden_kept": n_hidden,
        "third_party_removed": removed,
    }


def main():
    ap = argparse.ArgumentParser(description="Éclate une capture SingleFile.")
    ap.add_argument("capture", help="fichier .html produit par SingleFile")
    ap.add_argument("--out", default="site", help="dossier de sortie (défaut: site)")
    ap.add_argument("--keep-third-party", action="store_true",
                    help="conserver bandeau cookies, iframes vides, liens morts")
    a = ap.parse_args()

    if not os.path.isfile(a.capture):
        sys.exit(f"Introuvable : {a.capture}")

    r = run(a.capture, a.out, a.keep_third_party)

    print(f"\n  {a.capture}  ->  {a.out}/\n")
    print(f"  index.html      {r['html_ko']:8.0f} Ko")
    print(f"  style.css       {r['css_ko']:8.0f} Ko   ({r['css_blocks']} blocs <style> fusionnés)")
    print(f"  assets/img      {r['images']:8d} fichiers")
    print(f"  assets/fonts    {r['fonts']:8d} fichiers")
    print(f"  total assets    {r['assets_mo']:8.2f} Mo")
    if r["csp_removed"]:
        print(f"\n  meta CSP retirée : {r['csp_removed']}")
    if r["svg_inline"]:
        print(f"  SVG laissés inline dans le CSS : {r['svg_inline']}   "
              "(mask-image et filter: url() sont soumis au CORS)")
    if r["hidden_kept"]:
        print(f"  éléments .sf-hidden conservés : {r['hidden_kept']}   "
              "(invisibles via le CSS de SingleFile ; à réanimer dans app.js)")
    if r["third_party_removed"]:
        print("  résidus tiers retirés :")
        for k, v in r["third_party_removed"].items():
            print(f"    {v:3d}  {k}")
    print("\n  Étape suivante : copier js/app.js puis "
          "python3 tools/verify.py <capture> <out>/index.html\n")


if __name__ == "__main__":
    main()
