# Process — cloner une page à l'identique, sur n'importe quel site

Mode opératoire complet, de l'URL au repo poussé. Compter 15 à 25 minutes pour
une page qu'on n'a jamais vue, dont l'essentiel passe sur l'étape 4.

---

## Ce que le process garantit — et ce qu'il ne garantit pas

| | Récupérable | Comment |
|---|---|---|
| HTML rendu | oui, 100 % | SingleFile capture le DOM après exécution du JS |
| Textes | oui, 100 % | idem |
| Images | oui, 100 % | encodées en base64 dans la capture, réextraites en fichiers |
| Polices | oui, 100 % | idem |
| CSS | oui, 100 % | tous les blocs `<style>`, y compris media queries |
| **JavaScript** | **non, 0 %** | SingleFile le supprime. À réécrire — étape 4 |
| Formulaires | non | logique serveur |
| Widgets tiers | figés | le contenu de la date de capture, en dur |
| Suivi analytics | non | absent de la capture |

La distinction structurante : **le rendu se récupère, le comportement se
réécrit.** Tout le reste du process découle de là.

---

## Étape 1 — Capturer

Extension **SingleFile** (Chrome, Firefox, Edge, Safari — gratuite, open source).

1. Ouvrir la page cible.
2. Attendre le chargement **complet**. Descendre jusqu'en bas pour déclencher
   tout le lazy-loading, puis remonter. Une image non chargée est une image
   définitivement perdue.
3. Refuser ou accepter le bandeau cookies — mais le faire, sinon il est capturé
   par-dessus la page.
4. Cliquer le bouton SingleFile. `Ctrl+Shift+Y` par défaut.

Pour plusieurs pages d'un coup : clic droit sur le bouton, « traiter tous les
onglets ». Ou la CLI SingleFile en boucle sur une liste d'URL.

Renommer le fichier obtenu en `capture.html`.

## Étape 2 — Éclater

```bash
python3 tools/explode.py capture.html --out site
```

Le script sort un tableau : poids du HTML, du CSS, nombre de blocs `<style>`
fusionnés, nombre d'images et de polices extraites, résidus tiers retirés.

**Lire ce tableau, il oriente la suite.** Beaucoup de blocs `<style>` (plus de
30) signale un site à empilement de plugins : le CSS sera lourd et non
purgeable. Peu d'images extraites sur une page manifestement riche signale une
capture faite trop tôt — recommencer l'étape 1.

## Étape 3 — Inventorier les composants à réanimer

C'est le diagnostic qui conditionne l'étape 4. Trois commandes suffisent :

```bash
# sliders et carrousels
grep -o 'class="[^"]*swiper[^"]*"' site/index.html | sort -u | head -20

# tous les attributs data-* utilisés (révèle les widgets à comportement)
python3 - <<'EOF'
from bs4 import BeautifulSoup
import collections
s = BeautifulSoup(open('site/index.html', encoding='utf-8').read(), 'lxml')
c = collections.Counter(a for t in s.find_all() for a in t.attrs if a.startswith('data-'))
for k, v in c.most_common(30): print(f'{v:4d}  {k}')
EOF

# formulaires, iframes, éléments dépliables
grep -c '<form\|<iframe\|aria-expanded\|<details' site/index.html
```

Les signatures fréquentes :

| Ce qu'on voit | Ce que c'était | Mode dans `app.js` |
|---|---|---|
| `.swiper`, `.swiper-wrapper`, `.swiper-slide` | Swiper.js | `slide` |
| `swiper-fade` dans les classes | Swiper effet fondu | `fade` |
| `loop`, `marquee`, `ticker` dans les classes | bandeau défilant | `marquee` |
| `data-collapse-text`, `data-open-text` | « Lire la suite » | module collapse |
| `aria-expanded` + `aria-controls` | accordéon, FAQ | module accordéon |
| `data-wp-interactive` | API Interactivity de WordPress | menu mobile |
| `.elementor-*` | Elementor | onglets, accordéons, carrousels |
| `.ti-widget`, `.ti-review-content` | Trustindex | avis figés |

## Étape 4 — Réanimer

Copier le gabarit puis éditer **uniquement le bloc `CONFIG`** en haut du
fichier :

```bash
cp js/app.js site/js/app.js
```

```js
const CONFIG = {
  sliders: {
    '.mon-slider-hero':  { mode: 'fade' },
    '.bandeau-logos':    { mode: 'marquee', speed: 0.4 },
    '.carrousel-avis':   { mode: 'slide' },
  },
  sync: [['.slider-texte', '.slider-images']],
};
```

Ce qui est déjà générique et ne demande rien : détection automatique de tout
`.swiper` non déclaré, collapse, accordéons `aria-expanded`, menu mobile
WordPress, sous-menus au clavier, animations au scroll.

Vérifier dans la console du navigateur :

```js
__clone.report()
```

## Étape 5 — Vérifier

```bash
python3 tools/verify.py capture.html site/index.html
```

Quatre contrôles, du plus grave au plus fin :

1. **Assets** — toute requête en échec est une image perdue. Bloquant.
2. **JavaScript** — toute erreur console est un comportement cassé. Bloquant.
3. **Géométrie** — hauteur totale et hauteur de chaque section. Bloquant
   au-delà de 1 % d'écart, ajustable avec `--tolerance`.
4. **Pixels** — diff plein écran, avec la liste des zones divergentes.

Objectif : verdict **CONFORME**, plus de 98 % de pixels identiques.

### Lire un échec

| Symptôme | Cause quasi certaine | Correctif |
|---|---|---|
| N requêtes en échec, chemins en `../assets/` | `style.css` déplacé dans un sous-dossier | le remettre à la racine de `site/` |
| Page nue, CSS non appliqué | la balise CSP est revenue | la retirer du `<head>` |
| Une section fait +80 à +100 px | le CSS du site écrase le style inline du JS | `setProperty(prop, val, 'important')` |
| Section beaucoup plus haute, plusieurs centaines de px | slider en fondu dont les slides restent dans le flux | vérifier le `mode` dans `CONFIG` |
| Hauteur qui varie d'un run à l'autre | polices ou images encore en cours de chargement | augmenter `--wait` |
| −10 à −15 px sur le footer | iframes vides supprimées | attendu, ne pas chasser |

## Étape 6 — Livrer et pousser

```bash
python3 tools/merge.py site                # un fichier, assets externes
python3 tools/merge.py site --standalone   # un fichier, tout en base64
```

Puis :

```bash
git init && git add . && git commit -m "clone fidèle de <url> au <date>"
```

Pour travailler ensuite : **ouvrir le dossier avec Claude Code**, pas coller le
fichier fusionné dans un chat. `CLAUDE.md` briefe la session automatiquement,
et `verify.py` sert de garde-fou après chaque modification.

---

## Cas d'usage

**Refonte à partir de l'existant.** Le clone donne un point de départ qui
tourne, versionné, comparable au pixel. On modifie section par section en
gardant `verify.py` sous la main pour mesurer ce qui a bougé — un diff visuel
objectif au lieu d'un ressenti.

**Analyse de la concurrence.** Structure HTML, hiérarchie de titres, données
structurées, poids réel des pages, tout est là et local. Pour l'observation :
republier la page d'un tiers reste une contrefaçon.

**Migration de CMS.** Le clone est la référence de non-régression. On
reconstruit sur la nouvelle stack, on capture le résultat, on compare les deux
avec `verify.py`.

**Archivage d'une version.** Une capture par livraison. Le jour où un client
affirme que « c'était mieux avant », la comparaison est chiffrée.

## Limite à connaître d'avance

Une capture, c'est **une page, un viewport, un instant**. Pour du responsive,
capturer aux largeurs voulues et vérifier avec `--width`. Le site derrière
continue de vivre : un clone est daté, pas vivant.

## Cas particulier WordPress

Si la cible est un WordPress à thème blocs (FSE — chercher `wp-site-blocks`
dans le HTML) et que l'objectif est de **repousser dans ce même WordPress**,
ce process n'est pas le bon. Le code source réel, ce sont
`templates/*.html`, `parts/*.html` et `theme.json`, plus le contenu en block
markup en base. Passer par **Outils → Éditeur de site → Exporter**.

Ce process vaut pour : refonte vers une autre stack, statique, analyse,
archivage, non-régression.
