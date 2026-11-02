# CLAUDE.md

Contexte pour toute session Claude Code sur ce dépôt.

## Ce qu'est ce dépôt

Un clone fidèle de la page d'accueil d'**aurlane.fr**, reconstruit depuis une
capture SingleFile du 30 juillet 2026, plus le pipeline pour refaire l'opération.

`site/` contient la page clonée. `tools/` contient le pipeline. `capture.html`
est la capture d'origine : **c'est la référence, ne jamais la modifier.**

Le clone est *statique et daté*. Il sert de base de refonte, de référence de
non-régression avant migration, et d'archive de la version livrée. Il ne
remplace pas le WordPress de production.

## Règle d'or

Toute modification de `site/` doit être suivie de :

```bash
python3 tools/verify.py capture.html site/index.html   # fidélité au pixel
python3 tools/smoke.py  site/index.html                # les comportements répondent
```

Le premier compare assets, erreurs JS, hauteur de chaque section et pixels. Le
second pilote réellement les composants — une page parfaitement fidèle et
complètement morte passe `verify.py` sans une remarque. **Ne pas considérer une
tâche terminée sans un verdict CONFORME et un COMPORTEMENTS : OK**, sauf écart
volontaire, et alors le dire explicitement.

Référence actuelle, à ne pas dégrader :

| Contrôle | Résultat |
|---|---|
| Assets manquants | 0 |
| Erreurs console | 0 |
| Pixels identiques à 1440 px | 99,76 % (0,12 % nettement différents) |
| Hauteur totale à 1440 px | −78 px (0,78 %) |
| Pixels identiques à 390 px | 99,16 % |
| Comportements | 12/12 |

## Les écarts connus, et pourquoi ils sont normaux

Trois zones divergent de la capture. Aucune n'est un défaut, ne pas les chasser.

1. **Les deux widgets Trustpilot** (−20 px en tête, −150 px en pied) sont des
   `<iframe>` sans `src` : leur contenu est cross-origin, SingleFile ne peut pas
   le capturer. Le pipeline les retire, d'où les −78 px de hauteur totale. C'est
   la seule cause de l'écart de géométrie. À 390 px cet écart pèse 2,29 % et
   dépasse la tolérance par défaut : `--tolerance 2.5` rend alors CONFORME.

2. **Le bouton burger est présent dans le clone et absent de la capture.**
   C'est voulu, voir plus bas.

3. **Les carrousels sont réinitialisés à l'index 0**, la capture les avait figés
   ailleurs. Attendu sur tout clone.

## Ce que le clone corrige par rapport à la capture

Une capture n'est pas fidèle par nature : SingleFile perd des choses. Trois
réparations sont faites *sciemment*, et rendent le clone plus proche du site
réel que ne l'est la capture.

1. **Les éléments masqués sont conservés.** SingleFile marque `.sf-hidden` tout
   ce qui n'était pas affiché à l'instant de la capture, et injecte
   `.sf-hidden{display:none!important}`. Les jeter ne gagne pas un pixel et
   emporte des noeuds dont le comportement dépend. `explode.py` les garde ;
   `app.js` retire la classe sur les seuls noeuds qu'il réanime, et uniquement
   sur ceux que le CSS du site masque déjà seul au repos.

2. **21 images et les 4 vidéos ont été retéléchargées.** SingleFile a échoué à
   récupérer ces images et leur a substitué un SVG transparent — elles
   s'affichaient pourtant bien en production. `tools/fetch_missing.py` les
   rapatrie en local depuis `images.aurlane.fr`, et lit les `src` des `<source>`
   vidéo sur la page en ligne. Le clone reste consultable hors-ligne.

3. **Le bouton burger est reconstruit.** SingleFile vide les descendants d'un
   élément masqué *et* purge les règles CSS devenues inutilisées : le burger
   revenait en carré blanc vide. `app.js` lui rend ses trois
   `<span class="hamburger__bar">` et la règle telle qu'elle figure dans
   `aurlane-combined.css` en production.

## Points techniques à ne pas « corriger » par erreur

1. **`style.css` est à la racine de `site/`, pas dans un sous-dossier.**
   SingleFile déclare les images de fond dans des variables CSS
   (`--sf-img-42: url(assets/img/x.png)`). Le navigateur résout les URL
   relatives d'une custom property contre le **document**, pas contre la feuille
   de style. Déplacer `style.css` dans `site/css/` casse les images de fond,
   silencieusement.

2. **La balise `<meta http-equiv="Content-Security-Policy">` a été retirée.**
   SingleFile l'injecte ; elle bloque tout CSS et JS externe. La réintroduire
   rend la page nue.

3. **4 SVG restent inline dans `style.css`, ce n'est pas un oubli.**
   Ils servent à `mask-image`, qui est soumis au CORS — et deux fichiers
   `file://` sont cross-origin pour Chromium. Extraits en fichiers, ces masques
   sont bloqués et les icônes disparaissent. Inline, ils marchent partout.

4. **`fetch_missing.py` refuse les images d'une seule couleur.**
   Smash Balloon annonce dans `data-lazy-src` non pas la photo mais son
   `placeholder.png`, un aplat blanc **opaque** de 1000×560. Le récupérer
   remplacerait le SVG **transparent** de la capture et masquerait ce qu'il y a
   dessous : mesuré, cela coûtait 3,9 points de fidélité.

5. **`verify.py` attend le décodage des images, pas un délai fixe.**
   Sans cela, une grande photo décodée juste après la capture d'écran fait
   varier le résultat d'un run à l'autre — on se met alors à chasser un défaut
   de mise en page qui n'existe pas.

6. **Deux requêtes `.mp4` en `ERR_ABORTED` ne sont pas des assets perdus.**
   Le Chromium de Playwright est compilé sans codecs propriétaires : il
   abandonne le chargement d'un H.264 qu'il ne sait pas décoder. Les fichiers
   sont bien là et se lisent dans un navigateur normal. `verify.py` les classe
   comme non bloquants — un fichier présent sur le disque n'est pas perdu.

7. **Les deux `<video>` portent le même `id="video-1"`.**
   C'est un doublon d'identifiant présent en production. Conservé tel quel par
   fidélité.

## Ce qui est irrécupérable depuis une capture

Ces éléments vivent côté serveur. Ne pas essayer de les « réparer », les
recâbler sur la nouvelle stack :

- les deux `<form>` (recherche, newsletter) — `action` neutralisée en `#`,
  l'originale est conservée dans `data-original-action`
- la recherche produits en autocomplétion — le panneau `#search-panel-suggestions`
  est présent mais vide, son contenu venait d'une requête AJAX
- les avis Trustpilot — deux widgets, iframes cross-origin non capturables
- le panier WooCommerce, les prix, les stocks — figés à la date de capture
- le feed Instagram — les 24 posts sont figés ; le carrousel, lui, est réanimé
- le bandeau cookies (Complianz) — retiré
- GA4, GTM, tout le suivi

## Avant un déploiement

- `<link rel="canonical">` et `og:url` pointent encore vers `https://aurlane.fr/`
- les liens de navigation sont absolus vers la production
- les URL WordPress mortes (`/feed/`, `wp-json`, `xmlrpc.php`) ont déjà été
  retirées du `<head>`
- les données structurées Yoast décrivent toujours le site d'origine

## Structure

```
capture.html              capture SingleFile du 30/07/2026 — RÉFÉRENCE, en lecture seule
site/
  index.html              DOM rendu, nettoyé — 648 Ko
  style.css               les 57 blocs <style> concaténés — 452 Ko
  js/app.js               comportements réécrits en vanilla — 24 Ko
  assets/img/             68 images
  assets/fonts/           13 polices
  assets/video/           4 vidéos de bannière
tools/
  explode.py              capture -> projet éclaté
  fetch_missing.py        récupère ce que la capture n'a pas embarqué
  verify.py               contrôle de fidélité, sort en code 1 si échec
  smoke.py                contrôle que les comportements répondent
  preview.py              aperçu en direct avec rechargement automatique
  merge.py                projet -> fichier unique (livraison seulement)
js/app.js                 source des comportements, recopiée dans site/js/
PROCESS.md                le mode opératoire complet, de l'URL au dépôt poussé
```

## Reconstruire de zéro

Les quatre commandes sont rejouables et idempotentes ; `fetch_missing.py` ne
retélécharge pas un asset déjà présent.

```bash
pip install -r requirements.txt

python3 tools/explode.py capture.html --out site
python3 tools/fetch_missing.py site/index.html --from-live https://aurlane.fr/
cp js/app.js site/js/app.js
python3 tools/verify.py capture.html site/index.html
```

## Aperçu en direct pendant l'édition

```bash
python3 tools/preview.py            # sert site/ sur http://localhost:8000
```

L'onglet se recharge à chaque modification de `index.html`, `style.css` ou
`js/app.js`. Point d'entrée tout-en-un : `python3 reprendre.py capture.html`.

## Les comportements réanimés

Tout le JavaScript de production a été supprimé par SingleFile. `site/js/app.js`
le remplace en vanilla, sans dépendance. Son bloc `CONFIG`, en tête de fichier,
est la seule zone à éditer pour un autre site.

| Composant | Ce que c'était | Où |
|---|---|---|
| `.aurlane-product-carousel-container` | Swiper | `CONFIG.sliders`, mode `slide` |
| `.aurlane-testimonials-carousel-container` | Swiper | `CONFIG.sliders`, mode `slide` |
| menu mobile `#js-hamburger` / `#mobile-menu` | JS du thème | module Aurlane 2 |
| images du mega-menu, appariées par `data-item-id` | JS du thème | module Aurlane 3 |
| carrousel Instagram `.sbi_carousel` | Owl Carousel | module Aurlane 4 |
| lecture automatique des bannières vidéo | attribut + JS | module Aurlane 5 |

Les deux carrousels Aurlane portent `swiper-initialized` et `swiper-wrapper`
mais **jamais la classe `.swiper`** : la détection automatique ne les voit pas,
ils doivent rester déclarés dans `CONFIG`.

Le carrousel Instagram est piloté par un module dédié, et surtout **pas** par le
moteur générique : celui-ci pose une classe `.swiper-slide` sur chaque slide, et
le `.swiper-slide{width:100%}` présent dans `style.css` écraserait la largeur de
240 px des éléments Owl.

## Diagnostic dans le navigateur

Ouvrir `site/index.html`, puis dans la console :

```js
__clone.report()
```

Affiche les sliders réanimés avec leur mode et leur nombre de slides, plus l'état
des modules Aurlane.

## Pilotage SEO : méthode de Rémi Oravec

Toute session de pilotage SEO, de contenu, de roadmap ou de reporting sur ce client applique la méthode du pilote SEO Monkey.

- Charte complète : `CLAUDE.md` du dépôt `remioravec-seomonkey/PILOTE-SEO-MONKEY`
- Page de référence (schémas) : https://claude.ai/artifact/F4qUSVtVFgv1sRg63T7HEF

À retenir, à chaque fois :

- Claude est le chef de projet du client, responsable du ROI et de la clarté de la stratégie.
- Toute proposition passe en QCM. Rien n'est appliqué sans l'OK de Rémi.
- **Boucle vertueuse.** Mots-clés BOFU/MOFU, SERP gagnable (top 5, écart de domaines référents avec le top 3), ranking qui finance la suite. On part des pages qui vendent. La LTV n'est pas un critère.
- **Contenu** = optimisation sur le site de la page existante. **GEO** = article du cocon, qui ne doit pas cannibaliser son silo.
- **Cocon fermé.** Un guide par page mère : c'est la **page boost**, qui transmet le jus à la mère et aux filles.
- **Cartographie (11)** = 11 ancres distinctes par page cible. Les ancres sont semi-optimisées en majorité.
- **Surfer raisonnable** = emplacement du lien, dans le contenu principal, en haut, un lien par cible.
- **Netlinking** vers la page mère ou son guide, en ancre semi-optimisée.
- **SXO / NavBoost.**
  - Pyramide inversée, une image par Hn, des éléments interactifs complets si besoin.
  - Des pages authentiques, agréables, qui donnent envie d'agir et de revenir.
  - Un CTA visible en permanence.
- **Roadmaps et rendus** : on garde toujours la DA d'avant (colonnes, lignes, chips, mise en forme conditionnelle).
- **Fin de pilotage** : reporting Loom avec le skill `reporting-hebdo-loom`.
