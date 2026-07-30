#!/usr/bin/env python3
"""
reprendre.py — reprendre un site existant en une seule commande.

    python3 reprendre.py capture.html

Pour un consultant : déposer la capture SingleFile de la page, lancer cette
commande, et le navigateur s'ouvre sur le clone en direct. Ensuite, ouvrir ce
dossier dans Claude Code et demander les modifications en discutant : l'aperçu
se rafraîchit tout seul à chaque changement.

Ce que la commande enchaîne :
  1. éclate la capture en projet HTML / CSS / JS travaillable  (tools/explode.py)
  2. branche les comportements réécrits en vanilla             (js/app.js)
  3. contrôle la fidélité au pixel, si les dépendances sont là (tools/verify.py)
  4. ouvre l'aperçu en direct                                  (tools/preview.py)

Aucune API, aucune connexion sortante. L'étape 3 est sautée proprement si
Playwright n'est pas installé — elle n'est utile qu'à la personne qui retravaille
la page, pas au consultant qui la dépose.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def step(n: int, title: str) -> None:
    print(f"\n  [{n}/4] {title}")


def have_verify_deps() -> bool:
    try:
        import numpy  # noqa: F401
        import PIL  # noqa: F401
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Reprendre un site depuis une capture SingleFile.")
    ap.add_argument("capture", help="fichier .html produit par l'extension SingleFile")
    ap.add_argument("--out", default="site", help="dossier de sortie (défaut: site)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-open", action="store_true", help="ne pas ouvrir le navigateur")
    ap.add_argument("--no-verify", action="store_true", help="sauter le contrôle de fidélité")
    a = ap.parse_args()

    if not os.path.isfile(a.capture):
        sys.exit(f"Introuvable : {a.capture}\n"
                 "Déposer d'abord la capture SingleFile de la page dans ce dossier.")

    py = sys.executable
    tools = os.path.join(HERE, "tools")

    step(1, "Éclatement de la capture")
    r = subprocess.run([py, os.path.join(tools, "explode.py"), a.capture, "--out", a.out])
    if r.returncode != 0:
        sys.exit("L'éclatement a échoué. Manque-t-il beautifulsoup4 ? "
                 "-> pip install beautifulsoup4 lxml")

    step(2, "Branchement des comportements (js/app.js)")
    dst = os.path.join(a.out, "js")
    os.makedirs(dst, exist_ok=True)
    shutil.copyfile(os.path.join(HERE, "js", "app.js"), os.path.join(dst, "app.js"))
    print("      js/app.js copié dans " + os.path.join(a.out, "js"))

    step(3, "Contrôle de fidélité au pixel")
    if a.no_verify:
        print("      sauté (--no-verify)")
    elif not have_verify_deps():
        print("      sauté — Playwright/Pillow/NumPy absents.")
        print("      Facultatif ici ; utile à la personne qui retravaille la page :")
        print("      ./setup.sh puis python3 tools/verify.py " + a.capture + " " + a.out + "/index.html")
    else:
        subprocess.run([py, os.path.join(tools, "verify.py"), a.capture,
                        os.path.join(a.out, "index.html")])

    step(4, "Aperçu en direct")
    print("\n  Prêt. Pour retravailler la page : ouvrir ce dossier dans Claude Code")
    print("  et décrire les modifications voulues — l'aperçu se rafraîchit tout seul.\n")
    cmd = [py, os.path.join(tools, "preview.py"), a.out, "--port", str(a.port)]
    if a.no_open:
        cmd.append("--no-open")
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
