# aurlane.fr — clone fidèle de la page d'accueil

Reconstruction travaillable et versionnable de <https://aurlane.fr/>, à partir
d'une capture SingleFile du **30 juillet 2026**.

Le rendu est récupéré à 100 %. Le JavaScript, que SingleFile supprime, est
réécrit en vanilla : 24 Ko lisibles au lieu des bibliothèques d'origine.

```bash
pip install -r requirements.txt
python3 tools/preview.py          # http://localhost:8000
```

Pour retravailler la page, ouvrir ce dossier dans Claude Code : `CLAUDE.md`
briefe la session, et `tools/verify.py` sert de garde-fou après chaque
modification.

## Fidélité mesurée

| Contrôle | Résultat |
|---|---|
| Assets manquants | 0 |
| Erreurs console | 0 |
| Pixels identiques à 1440 px | **99,76 %** |
| Pixels identiques à 390 px | **99,16 %** |
| Écart de hauteur totale | −78 px (0,78 %) |
| Comportements pilotés | 12/12 |

Les −78 px sont les deux widgets Trustpilot, des `<iframe>` cross-origin que
SingleFile ne peut pas capturer et que le pipeline retire. C'est la seule cause
de l'écart de géométrie.

## Contrôler

```bash
python3 tools/verify.py capture.html site/index.html   # fidélité au pixel
python3 tools/smoke.py  site/index.html                # les comportements répondent
```

`verify.py` prouve que la page est identique à la capture. Il ne prouve rien sur
ce qui bouge : une page parfaitement fidèle et complètement morte passe le
contrôle sans une remarque. `smoke.py` couvre cet angle mort en cliquant les
flèches, en survolant les liens du mega-menu et en ouvrant le menu mobile.

## Reconstruire de zéro

```bash
python3 tools/explode.py capture.html --out site
python3 tools/fetch_missing.py site/index.html --from-live https://aurlane.fr/
cp js/app.js site/js/app.js
python3 tools/verify.py capture.html site/index.html
```

## Ce que ce dépôt n'est pas

Un clone est **daté, statique, et lié à un viewport**. Les formulaires, le
panier, les prix, la recherche et les avis vivent côté serveur : ils sont figés
au 30 juillet 2026. Le détail de ce qui est récupérable et de ce qui ne l'est
pas est dans `CLAUDE.md`, le mode opératoire complet dans `PROCESS.md`.

Ce dépôt sert à trois choses : partir de l'existant pour une refonte, servir de
référence de non-régression avant une migration, et archiver une version livrée.
Il ne sert pas à repousser du code dans le WordPress de production.
