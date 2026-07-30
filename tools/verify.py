#!/usr/bin/env python3
"""
verify.py — prouve que la reconstruction est identique à la capture d'origine.

    python3 tools/verify.py capture.html site/index.html [--width 1440] [--shots]

Contrôle quatre choses, dans l'ordre de gravité :

  1. ASSETS      toute requête en échec = une image ou une police perdue
  2. JS          toute erreur console = un comportement cassé
  3. GÉOMÉTRIE   hauteur totale + hauteur de chaque section de premier niveau
  4. PIXELS      diff plein écran, en ignorant les zones connues pour bouger
                 (sliders animés, bandeaux défilants)

Sort en code 1 si un contrôle bloquant échoue : utilisable en pre-commit.

Les écarts de géométrie sont le signal le plus utile. Un slider réécrit qui
fait 90 px de plus que l'original révèle presque toujours qu'une propriété
CSS du site (display:grid, flex-wrap:wrap) écrase le style inline posé par
le JS — il faut alors passer par setProperty(..., 'important').
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

SETTLE_JS = """async () => {
  window.scrollTo(0, document.body.scrollHeight);
  window.scrollTo(0, 0);
  try { await document.fonts.ready; } catch (e) {}
  const imgs = Array.from(document.images);
  await Promise.all(imgs.map(i => {
    if (i.decode) return i.decode().catch(() => {});
    if (i.complete) return null;
    return new Promise(r => { i.onload = i.onerror = r; });
  }));
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
}"""

GEOMETRY_JS = """() => {
  const out = [];
  const seen = new Set();
  const sel = ['body > *', '.wp-site-blocks > *', '.entry-content > *',
               'main > *', 'header', 'footer', 'section'];
  sel.forEach(s => document.querySelectorAll(s).forEach((el, i) => {
    const cls = (typeof el.className === 'string' ? el.className : '')
                  .split(' ').filter(Boolean)[0] || '_';
    const key = el.tagName.toLowerCase() + '.' + cls + '#' + s + i;
    if (seen.has(key)) return;
    seen.add(key);
    const r = el.getBoundingClientRect();
    if (r.height < 2) return;
    out.push([key, Math.round(r.height)]);
  }));
  return { total: document.documentElement.scrollHeight, nodes: out };
}"""


def chromium_path() -> str | None:
    """Chromium à utiliser, quand celui du cache Playwright ne correspond pas.

    Un environnement qui préinstalle Chromium (PLAYWRIGHT_BROWSERS_PATH) fournit
    souvent un build différent de celui que réclame la version de playwright
    installée. Plutôt que de retélécharger, on réutilise le binaire présent.
    CHROMIUM_PATH permet de forcer un chemin à la main.
    """
    import glob
    forced = os.environ.get("CHROMIUM_PATH")
    if forced:
        return forced if os.path.isfile(forced) else None
    root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if not root:
        return None
    for pat in ("chromium-*/chrome-linux/chrome",
                "chromium/chrome-linux/chrome",
                "chromium_headless_shell-*/chrome-linux/headless_shell"):
        hits = sorted(glob.glob(os.path.join(root, pat)))
        if hits:
            return hits[-1]
    return None


async def probe(page_path: str, width: int, wait: int):
    from playwright.async_api import async_playwright
    failed, errors = [], []
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch()
        except Exception:
            exe = chromium_path()
            if not exe:
                raise
            browser = await p.chromium.launch(executable_path=exe)
        page = await browser.new_page(viewport={"width": width, "height": 1000})
        page.on("requestfailed",
                lambda r: failed.append((r.url, r.failure or "")))
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console",
                lambda m: errors.append(m.text) if m.type == "error" else None)
        await page.goto("file://" + os.path.abspath(page_path))
        # Un simple délai ne suffit pas : une grande photo décodée juste après
        # la capture d'écran fait varier le résultat d'un run à l'autre, et on
        # se met alors à chasser un défaut de mise en page qui n'existe pas.
        # On attend donc que les polices soient prêtes et que chaque image soit
        # réellement décodée, puis seulement le délai demandé.
        await page.evaluate(SETTLE_JS)
        await page.wait_for_timeout(wait)
        geo = await page.evaluate(GEOMETRY_JS)
        shot = await page.screenshot(full_page=True)
        await browser.close()
    return {"failed": failed, "errors": errors, "geo": geo, "shot": shot}


def pixel_diff(a_png: bytes, b_png: bytes, tag: str):
    try:
        import io
        import numpy as np
        from PIL import Image
    except ImportError:
        return None
    a = Image.open(io.BytesIO(a_png)).convert("RGB")
    b = Image.open(io.BytesIO(b_png)).convert("RGB")
    h, w = min(a.height, b.height), min(a.width, b.width)
    A = np.asarray(a.crop((0, 0, w, h)), dtype=np.int16)
    B = np.asarray(b.crop((0, 0, w, h)), dtype=np.int16)
    d = np.abs(A - B).sum(axis=2)
    rows = (d > 60).mean(axis=1)
    bad = [i for i, v in enumerate(rows) if v > 0.15]
    zones = []
    if bad:
        s = p = bad[0]
        for i in bad[1:]:
            if i - p > 60:
                zones.append((s, p))
                s = i
            p = i
        zones.append((s, p))
    return {
        "same": 100 * float((d <= 15).mean()),
        "diff": 100 * float((d > 60).mean()),
        "zones": zones,
        "size_a": a.size,
        "size_b": b.size,
    }


async def main_async(a):
    print("\n  rendu de la capture d'origine…")
    A = await probe(a.capture, a.width, a.wait)
    print("  rendu de la reconstruction…")
    B = await probe(a.rebuild, a.width, a.wait)

    fail = False
    print("\n" + "=" * 62)
    print("  1. ASSETS")
    print("=" * 62)
    # Une requête en échec ne vaut alerte que si le fichier manque vraiment.
    # Un <video> H.264 abandonne son chargement (ERR_ABORTED) sur un Chromium
    # compilé sans codecs propriétaires, celui de Playwright par exemple : le
    # fichier est là, il est simplement indécodable ICI. Ce n'est pas un asset
    # perdu, et l'annoncer comme tel masquerait les vrais.
    lost, aborted = [], []
    for url, why in B["failed"]:
        path = url[7:].split("?")[0] if url.startswith("file://") else None
        (aborted if path and os.path.isfile(path) else lost).append((url, why))

    if lost:
        fail = True
        print(f"  ECHEC — {len(lost)} asset(s) introuvable(s) :")
        for u, why in lost[:12]:
            print(f"      {u.split('/')[-1]}   {why}")
    else:
        print("  OK — aucun asset manquant")
    if aborted:
        print(f"\n  {len(aborted)} requête(s) interrompue(s) sur un fichier bien "
              "présent, non bloquant :")
        for u, why in aborted[:8]:
            print(f"      {u.split('/')[-1]}   {why}")
        print("      Cause usuelle : Chromium sans codecs propriétaires (mp4/H.264).")

    print("\n" + "=" * 62)
    print("  2. JAVASCRIPT")
    print("=" * 62)
    if B["errors"]:
        fail = True
        print(f"  ECHEC — {len(B['errors'])} erreur(s) :")
        for e in B["errors"][:8]:
            print("      " + e[:100])
    else:
        print("  OK — aucune erreur console")

    print("\n" + "=" * 62)
    print("  3. GEOMETRIE")
    print("=" * 62)
    ta, tb = A["geo"]["total"], B["geo"]["total"]
    delta = tb - ta
    pct = 100 * abs(delta) / max(ta, 1)
    print(f"  hauteur totale   {ta:7d} px  ->  {tb:7d} px   "
          f"écart {delta:+d} px ({pct:.2f} %)")
    if pct > a.tolerance:
        fail = True
        print(f"  ECHEC — au-delà de la tolérance de {a.tolerance} %")

    ga = dict(A["geo"]["nodes"])
    gb = dict(B["geo"]["nodes"])
    diffs = [(k, ga[k], gb[k]) for k in ga if k in gb and abs(gb[k] - ga[k]) > 4]
    if diffs:
        print(f"\n  {len(diffs)} section(s) de hauteur différente :")
        print(f"  {'section':44}{'orig':>8}{'new':>8}{'écart':>8}")
        for k, x, y in sorted(diffs, key=lambda t: -abs(t[2] - t[1]))[:15]:
            print(f"  {k.split('#')[0][:44]:44}{x:8d}{y:8d}{y-x:+8d}")
    else:
        print("  OK — toutes les sections communes ont la même hauteur")

    print("\n" + "=" * 62)
    print("  4. PIXELS")
    print("=" * 62)
    px = pixel_diff(A["shot"], B["shot"], "full")
    if px is None:
        print("  ignoré (pip install pillow numpy pour l'activer)")
    else:
        print(f"  capture      {px['size_a'][0]} x {px['size_a'][1]}")
        print(f"  reconstruite {px['size_b'][0]} x {px['size_b'][1]}")
        print(f"  pixels identiques           {px['same']:6.2f} %")
        print(f"  pixels nettement différents {px['diff']:6.2f} %")
        if px["zones"]:
            print("  zones divergentes (y, en px de l'image) :")
            for z in px["zones"][:10]:
                print(f"      {z[0]:7d} -> {z[1]:7d}")
            print("  Note : un slider réinitialisé à l'index 0 et un bandeau"
                  " défilant\n         divergent toujours. C'est attendu,"
                  " pas un défaut.")

    if a.shots:
        for label, data in (("capture", A["shot"]), ("rebuild", B["shot"])):
            p = f"verify_{label}.png"
            open(p, "wb").write(data)
            print(f"\n  capture d'écran écrite : {p}")

    print("\n" + "=" * 62)
    print("  VERDICT : " + ("ECHEC" if fail else "CONFORME"))
    print("=" * 62 + "\n")
    return 1 if fail else 0


def main():
    ap = argparse.ArgumentParser(description="Vérifie la fidélité d'une reconstruction.")
    ap.add_argument("capture", help="capture SingleFile d'origine")
    ap.add_argument("rebuild", help="index.html reconstruit")
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--wait", type=int, default=4000, help="ms d'attente après chargement")
    ap.add_argument("--tolerance", type=float, default=1.0,
                    help="écart de hauteur toléré, en %% (défaut 1)")
    ap.add_argument("--shots", action="store_true", help="écrire les deux captures PNG")
    a = ap.parse_args()
    for f in (a.capture, a.rebuild):
        if not os.path.isfile(f):
            sys.exit(f"Introuvable : {f}")
    sys.exit(asyncio.run(main_async(a)))


if __name__ == "__main__":
    main()
