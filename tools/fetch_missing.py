#!/usr/bin/env python3
"""
fetch_missing.py — récupère les assets qu'une capture SingleFile n'a pas embarqués.

    python3 tools/fetch_missing.py site/index.html
    python3 tools/fetch_missing.py site/index.html --from-live https://aurlane.fr/

Deux trous sont fréquents dans une capture, et aucun des deux ne se voit à la
lecture du rendu :

  1. Une image en lazy-load jamais entrée dans le viewport n'a jamais été
     téléchargée par le navigateur. SingleFile n'a donc rien à encoder : il
     laisse src="data:," et l'URL réelle dans data-lazy-src. Symptôme typique
     sur les images d'un mega-menu, affichées au survol d'un lien.

  2. SingleFile n'embarque pas les vidéos. Les <source> perdent leur src et ne
     gardent que type et media. La <video> n'affiche plus que son poster.

Le script comble les deux, et écrit les fichiers en local : le clone doit rester
consultable hors-ligne, donc on ne se contente pas de recâbler vers le CDN.

Les <source> n'ont plus aucune URL à récupérer dans la capture : elles sont
lues sur la page en ligne (--from-live), en appariant les <video> dans l'ordre
du document puis les <source> par leur attribut media. Rien n'est codé en dur.
Sans --from-live, l'étape vidéo est simplement annoncée et sautée.

Le script est idempotent : un asset déjà présent en local n'est pas retéléchargé.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import urllib.request
from urllib.parse import urlparse

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Il manque beautifulsoup4 : pip install beautifulsoup4 lxml")

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"

# attributs où un lazy-loader range l'URL réelle
LAZY_ATTRS = ("data-lazy-src", "data-src", "data-original", "data-lazy-srcset")

# un src qui ne pointe vers rien d'exploitable
PLACEHOLDER = re.compile(r"^\s*$|^data:,|^data:image/(?:gif|png);base64,R0lGOD|^data:image/svg\+xml,")

EXT_OK = {"webp", "png", "jpg", "jpeg", "avif", "gif", "svg", "mp4", "webm", "mov"}


def get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def local_name(url: str, folder: str) -> str:
    """Nom stable et court, sur le modèle de celui qu'écrit explode.py."""
    key = hashlib.sha1(url.encode()).hexdigest()[:12]
    ext = os.path.splitext(urlparse(url).path)[1].lstrip(".").lower()
    if ext not in EXT_OK:
        ext = "mp4" if folder == "video" else "webp"
    return f"assets/{folder}/{key}.{ext}"


def is_blank_image(path: str) -> bool:
    """Vrai si l'image est d'une seule couleur, donc sans aucune information.

    Certains lazy-loaders rangent dans data-lazy-src non pas la vraie image mais
    le placeholder du plugin — Smash Balloon sert un placeholder.png blanc de
    1000x560. Le récupérer remplacerait le SVG transparent de la capture par un
    aplat opaque, qui masquerait ce qu'il y a dessous : c'est une régression
    déguisée en récupération. Mieux vaut ne rien toucher.
    """
    try:
        from PIL import Image
    except ImportError:
        return False
    if path.lower().endswith(".svg"):
        return False
    try:
        with Image.open(path) as im:
            extrema = im.convert("RGBA").getextrema()
    except Exception:
        return False
    return all(lo == hi for lo, hi in extrema)


def save(url: str, out_dir: str, folder: str) -> tuple[str | None, int, bool]:
    """Télécharge si absent. Renvoie (chemin relatif, octets, déjà_là)."""
    rel = local_name(url, folder)
    dst = os.path.join(out_dir, rel)
    if os.path.isfile(dst) and os.path.getsize(dst) > 0:
        return rel, os.path.getsize(dst), True
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        data = get(url)
    except Exception as e:
        print(f"      ECHEC  {url}\n             {e}")
        return None, 0, False
    if not data:
        print(f"      VIDE   {url}")
        return None, 0, False
    with open(dst, "wb") as f:
        f.write(data)
    return rel, len(data), False


# ------------------------------------------------------------------ images
def fix_images(soup: BeautifulSoup, out_dir: str) -> dict:
    n_ok = n_fail = n_skip = n_blank = total = 0
    blank_urls: set[str] = set()
    for img in soup.find_all("img"):
        src = img.get("src") or ""
        if src and not PLACEHOLDER.match(src):
            continue                                    # déjà servi en local
        url = next((img.get(a) for a in LAZY_ATTRS
                    if (img.get(a) or "").startswith("http")), None)
        if not url:
            continue
        url = url.split()[0].rstrip(",")                 # tolère un srcset
        if url in blank_urls:
            n_blank += 1
            continue
        rel, size, cached = save(url, out_dir, "img")
        if not rel:
            n_fail += 1
            continue
        if is_blank_image(os.path.join(out_dir, rel)):
            blank_urls.add(url)
            os.remove(os.path.join(out_dir, rel))
            n_blank += 1
            continue
        img["src"] = rel
        img["data-recovered-from"] = url
        # un srcset résiduel l'emporterait sur le src qu'on vient de poser
        for a in ("srcset", "data-lazy-srcset"):
            if img.get(a):
                del img[a]
        if cached:
            n_skip += 1
        else:
            n_ok += 1
            total += size
    return {"ok": n_ok, "cached": n_skip, "fail": n_fail, "bytes": total,
            "blank": n_blank, "blank_urls": len(blank_urls)}


# ------------------------------------------------------------------ vidéos
def live_video_sources(url: str) -> list[list[dict]]:
    """Lit la page en ligne et renvoie, par <video>, la liste de ses <source>."""
    soup = BeautifulSoup(get(url).decode("utf-8", "replace"), "lxml")
    out = []
    for v in soup.find_all("video"):
        out.append([{"src": s.get("src") or "",
                     "media": (s.get("media") or "").strip(),
                     "type": s.get("type") or ""}
                    for s in v.find_all("source")])
    return out


def fix_videos(soup: BeautifulSoup, out_dir: str, live: str | None) -> dict:
    videos = soup.find_all("video")
    holes = [v for v in videos if any(not s.get("src") for s in v.find_all("source"))]
    if not holes:
        return {"ok": 0, "cached": 0, "fail": 0, "bytes": 0, "holes": 0}
    if not live:
        print(f"      {len(holes)} <video> sans source — relancer avec "
              "--from-live <url de la page> pour les récupérer")
        return {"ok": 0, "cached": 0, "fail": 0, "bytes": 0, "holes": len(holes)}

    ref = live_video_sources(live)
    if len(ref) != len(videos):
        print(f"      la page en ligne expose {len(ref)} <video> contre {len(videos)} "
              "dans le clone — appariement refusé, rien n'est touché")
        return {"ok": 0, "cached": 0, "fail": 0, "bytes": 0, "holes": len(holes)}

    n_ok = n_fail = n_skip = total = 0
    for v, refs in zip(videos, ref):
        for s in v.find_all("source"):
            if s.get("src"):
                continue
            media = (s.get("media") or "").strip()
            # appariement par media query, sinon par type, sinon par ordre
            cand = next((r for r in refs if r["media"] == media and r["src"]), None) \
                or next((r for r in refs if r["type"] == (s.get("type") or "") and r["src"]), None)
            if not cand:
                print(f"      pas de correspondance en ligne pour media={media!r}")
                n_fail += 1
                continue
            rel, size, cached = save(cand["src"], out_dir, "video")
            if not rel:
                n_fail += 1
                continue
            s["src"] = rel
            s["data-recovered-from"] = cand["src"]
            if cached:
                n_skip += 1
            else:
                n_ok += 1
                total += size
    return {"ok": n_ok, "cached": n_skip, "fail": n_fail, "bytes": total,
            "holes": len(holes)}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Récupère les assets absents d'une capture SingleFile.")
    ap.add_argument("page", help="site/index.html produit par explode.py")
    ap.add_argument("--from-live", metavar="URL",
                    help="page en ligne d'où lire les src des <source> vidéo")
    a = ap.parse_args()

    if not os.path.isfile(a.page):
        sys.exit(f"Introuvable : {a.page}")
    out_dir = os.path.dirname(os.path.abspath(a.page))

    soup = BeautifulSoup(open(a.page, encoding="utf-8").read(), "lxml")

    print("\n  [1/2] Images en lazy-load jamais téléchargées")
    im = fix_images(soup, out_dir)
    print(f"      {im['ok']} récupérées, {im['cached']} déjà en local, "
          f"{im['fail']} en échec, {im['bytes']/1024/1024:.2f} Mo")
    if im["blank"]:
        print(f"      {im['blank']} laissées en place : l'URL annoncée sert un "
              f"aplat uni ({im['blank_urls']} placeholder(s) de plugin)")

    print("  [2/2] Sources vidéo")
    vi = fix_videos(soup, out_dir, a.from_live)
    print(f"      {vi['ok']} récupérées, {vi['cached']} déjà en local, "
          f"{vi['fail']} en échec, {vi['bytes']/1024/1024:.2f} Mo")

    with open(a.page, "w", encoding="utf-8") as f:
        f.write(str(soup))

    fails = im["fail"] + vi["fail"]
    print(f"\n  {a.page} réécrit." + ("" if not fails else f"  {fails} asset(s) en échec."))
    print("  Étape suivante : python3 tools/verify.py capture.html "
          f"{a.page}\n")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
