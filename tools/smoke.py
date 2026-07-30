#!/usr/bin/env python3
"""
smoke.py — vérifie que les comportements réécrits dans app.js répondent vraiment.

    python3 tools/smoke.py site/index.html [--width 1440] [--mobile-width 390]

verify.py prouve que la page est identique à la capture. Il ne prouve rien sur
ce qui bouge : une page parfaitement fidèle et complètement morte passe le
contrôle de fidélité sans une remarque. Ce script complète l'angle mort en
pilotant les composants pour de bon — clic sur la flèche d'un carrousel, survol
d'un lien de mega-menu, ouverture du menu mobile — et en mesurant que l'état
a changé.

Sort en code 1 si un comportement attendu ne répond pas.
"""
from __future__ import annotations

import argparse
import asyncio
import glob
import os
import sys


def chromium_path() -> str | None:
    forced = os.environ.get("CHROMIUM_PATH")
    if forced:
        return forced if os.path.isfile(forced) else None
    root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if not root:
        return None
    for pat in ("chromium-*/chrome-linux/chrome", "chromium/chrome-linux/chrome"):
        hits = sorted(glob.glob(os.path.join(root, pat)))
        if hits:
            return hits[-1]
    return None


async def launch(p):
    try:
        return await p.chromium.launch()
    except Exception:
        exe = chromium_path()
        if not exe:
            raise
        return await p.chromium.launch(executable_path=exe)


def row(label: str, ok: bool | None, detail: str = "") -> bool:
    mark = "OK   " if ok else ("  --  " if ok is None else "ECHEC")
    print(f"  {mark}  {label:44}{detail}")
    return ok is not False


async def run(a) -> int:
    from playwright.async_api import async_playwright

    url = "file://" + os.path.abspath(a.page)
    ok = True

    async with async_playwright() as p:
        browser = await launch(p)

        # ------------------------------------------------------------ desktop
        page = await browser.new_page(viewport={"width": a.width, "height": 1000})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(url)
        await page.wait_for_timeout(a.wait)

        print("\n  DESKTOP  " + f"{a.width}px")
        print("  " + "-" * 62)

        ok &= row("app.js chargé", await page.evaluate("() => !!window.__clone"))

        # carrousels : la flèche suivante doit déplacer le rail
        carousels = await page.evaluate(
            """() => Array.from(document.querySelectorAll(
                 '.aurlane-product-carousel-container,.aurlane-testimonials-carousel-container'
               )).map(c => c.className.split(' ')[0])"""
        )
        for cls in carousels:
            sel = f".{cls}"
            before = await page.evaluate(
                f"() => (document.querySelector('{sel} .swiper-wrapper')||{{style:{{}}}}).style.transform || ''")
            await page.click(f"{sel} .swiper-button-next", timeout=4000)
            await page.wait_for_timeout(700)
            after = await page.evaluate(
                f"() => (document.querySelector('{sel} .swiper-wrapper')||{{style:{{}}}}).style.transform || ''")
            ok &= row(f"carrousel {cls[:34]}", before != after, f"{before or 'aucun'} -> {after or 'aucun'}")

        # mega-menu : survol d'un lien -> l'image active change
        mega = await page.query_selector(".mega")
        if mega:
            # le mega-menu n'est déplié que par :hover/:focus-within sur son
            # entrée de menu : sans ce survol préalable, les liens ne sont pas
            # rendus et aucun mouseenter ne partirait.
            await page.hover("li.has-mega > a")
            await page.wait_for_timeout(400)

            links = await page.query_selector_all(
                "li.has-mega:first-of-type .mega .mega-menu-links > li > a[data-item-id]")
            before = await page.evaluate(
                """() => (document.querySelector(
                     'li.has-mega:first-of-type .mega .mega-menu-link-image.active'
                   )||{}).dataset?.itemId || ''""")
            target = None
            for l in links:
                iid = await l.get_attribute("data-item-id")
                if iid and iid != before:
                    target = (l, iid)
                    break
            if target:
                await target[0].hover(force=True)
                await page.wait_for_timeout(300)
                after = await page.evaluate(
                    """() => (document.querySelector(
                         'li.has-mega:first-of-type .mega .mega-menu-link-image.active'
                       )||{}).dataset?.itemId || ''""")
                ok &= row("mega-menu : image suit le lien survolé",
                          after == target[1], f"{before} -> {after}")
            else:
                ok &= row("mega-menu : image suit le lien survolé", None, "aucun lien distinct")

            # les images récupérées doivent avoir des pixels, pas un placeholder
            broken = await page.evaluate(
                """() => Array.from(document.querySelectorAll('img.mega-menu-link-image'))
                       .filter(i => i.complete && i.naturalWidth === 0).length""")
            ok &= row("images de mega-menu décodées", broken == 0, f"{broken} cassée(s)")

        # carrousel Instagram
        if await page.query_selector(".sbi_carousel .sbi-owl-next"):
            before = await page.evaluate(
                "() => document.querySelector('.sbi-owl-stage').style.transform")
            await page.click(".sbi_carousel .sbi-owl-next")
            await page.wait_for_timeout(600)
            after = await page.evaluate(
                "() => document.querySelector('.sbi-owl-stage').style.transform")
            ok &= row("carrousel Instagram", before != after, f"{before} -> {after}")

        # vidéos : les sources doivent pointer sur des fichiers locaux
        srcs = await page.evaluate(
            """() => Array.from(document.querySelectorAll('video source')).map(s => s.getAttribute('src'))""")
        ok &= row("sources vidéo locales",
                  bool(srcs) and all(s and s.startswith("assets/") for s in srcs),
                  f"{len(srcs)} source(s)")

        ok &= row("aucune erreur JS", not errors, "; ".join(errors[:2]))
        await page.close()

        # ------------------------------------------------------------- mobile
        page = await browser.new_page(viewport={"width": a.mobile_width, "height": 800})
        await page.goto(url)
        await page.wait_for_timeout(a.wait)

        print(f"\n  MOBILE   {a.mobile_width}px")
        print("  " + "-" * 62)

        burger = await page.query_selector("#js-hamburger")
        if not burger:
            ok &= row("bouton burger présent", False, "#js-hamburger absent du DOM")
        else:
            vis = await burger.is_visible()
            ok &= row("bouton burger visible", vis)
            if vis:
                await burger.click()
                await page.wait_for_timeout(500)
                opened = await page.evaluate(
                    """() => {
                         const i = document.querySelector('.mobile-menu__inner');
                         const r = i.getBoundingClientRect();
                         return r.left > -5 && r.width > 100;
                       }""")
                ok &= row("le menu mobile s'ouvre", opened)

                # sous-menu dépliant
                sub = await page.query_selector(".mobile-menu-main li.menu-item-has-children > a")
                if sub:
                    await sub.click()
                    await page.wait_for_timeout(500)
                    h = await page.evaluate(
                        """() => {
                             const s = document.querySelector(
                               '.mobile-menu-main li.menu-item-has-children > ul.sub-menu');
                             return s ? s.getBoundingClientRect().height : 0;
                           }""")
                    ok &= row("le sous-menu se déplie", h > 10, f"{h:.0f} px")

                await page.click("#js-mobile-menu-close")
                await page.wait_for_timeout(500)
                closed = await page.evaluate(
                    "() => document.querySelector('.mobile-menu__inner').getBoundingClientRect().right <= 5")
                ok &= row("le menu mobile se referme", closed)

        await page.close()
        await browser.close()

    print("\n  " + "=" * 62)
    print("  COMPORTEMENTS : " + ("OK" if ok else "ECHEC"))
    print("  " + "=" * 62 + "\n")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(
        description="Vérifie que les comportements réécrits répondent.")
    ap.add_argument("page", nargs="?", default="site/index.html")
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--mobile-width", type=int, default=390)
    ap.add_argument("--wait", type=int, default=2500)
    a = ap.parse_args()
    if not os.path.isfile(a.page):
        sys.exit(f"Introuvable : {a.page}")
    sys.exit(asyncio.run(run(a)))


if __name__ == "__main__":
    main()
