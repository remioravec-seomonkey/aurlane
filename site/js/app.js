/* ============================================================================
   app.js — réanimation d'une page capturée par SingleFile
   ----------------------------------------------------------------------------
   SingleFile conserve le DOM rendu et la totalité du CSS, mais SUPPRIME tout
   le JavaScript. La page est donc parfaite et morte. Ce fichier lui rend ses
   comportements, en vanilla, sans aucune dépendance.

   Principe : on ne réimplémente pas Swiper, on reproduit ses CLASSES D'ÉTAT
   (swiper-slide-active, swiper-slide-next, swiper-slide-prev) pour que le CSS
   déjà présent dans style.css continue de s'appliquer tel quel. 9 Ko au lieu
   des ~150 Ko de la bibliothèque.

   ORGANISATION
   ├── CONFIG        surcharges par site — la seule zone à éditer
   ├── Slider        moteur slide / fade / marquee
   ├── détection     auto-découverte des composants présents dans la page
   └── modules       collapse, sous-menus, accordéons, animations au scroll

   PIÈGE PRINCIPAL, valable sur tout site un peu habillé :
   le CSS du site peut écraser les styles inline posés ici. Sur un thème
   WordPress à blocs, une galerie est en display:grid et flex-wrap:wrap, ce qui
   fait passer un bandeau défilant sur deux lignes. Toujours forcer la mise en
   page d'un rail avec setProperty(prop, value, 'important').
   ========================================================================== */

(() => {
  'use strict';

  /* ======================================================== CONFIG ========= */
  /* Sélecteur -> mode. Éditer ici, et ici seulement, pour un nouveau site.
     Modes : 'slide' (translation), 'fade' (fondu), 'marquee' (défilement continu)
     Laisser vide pour tout laisser à la détection automatique.               */
  /* Aurlane — les deux carrousels portent swiper-initialized et swiper-wrapper
     mais jamais la classe .swiper elle-même : la détection automatique de
     l'étape 2 ne les voit pas, il faut les déclarer ici.                     */
  const CONFIG = {
    sliders: {
      '.aurlane-product-carousel-container':      { mode: 'slide' },
      '.aurlane-testimonials-carousel-container': { mode: 'slide' },
    },
    // paires de sliders à faire avancer ensemble
    sync: [],
  };

  /* ========================================================= UTILS ========= */
  const $  = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const reduced = () =>
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ======================================================== SLIDER ========= */

  class Slider {
    constructor(root, opts = {}) {
      this.root = root;
      this.wrapper =
        $('.swiper-wrapper', root) ||
        $('[class*="wrapper"]', root) ||
        root.firstElementChild;
      if (!this.wrapper) return;

      this.slides = Array.from(this.wrapper.children).filter(n => n.nodeType === 1);
      if (this.slides.length < 2) return;

      this.mode  = opts.mode  || 'slide';
      this.speed = opts.speed || (this.mode === 'marquee' ? 0.4 : 500);
      this.index = 0;
      this.linked = [];
      this.ok = true;

      this.slides.forEach(s => s.classList.add('swiper-slide'));
      root.classList.add('swiper-initialized');

      if (this.mode === 'marquee') return this.marquee();

      this.wrapper.style.transitionProperty = 'transform';
      this.wrapper.style.transitionTimingFunction = 'cubic-bezier(.25,.1,.25,1)';
      this.bindControls();
      this.bindSwipe();
      this.go(0, false);
      window.addEventListener('resize', () => this.go(this.index, false));
    }

    /* -- rail défilant en boucle (logos clients, bandeau de marques) -------- */
    marquee() {
      const track = this.wrapper;
      // le CSS du site impose souvent display:grid ici : on force le rail
      track.style.setProperty('display', 'flex', 'important');
      track.style.setProperty('flex-wrap', 'nowrap', 'important');
      track.style.setProperty('align-items', 'center', 'important');
      track.style.willChange = 'transform';
      this.slides.forEach(s => {
        s.style.setProperty('flex', '0 0 auto', 'important');
        track.appendChild(s.cloneNode(true));   // duplication = boucle sans couture
      });
      if (reduced()) return;
      let x = 0;
      const step = () => {
        const half = track.scrollWidth / 2;
        x = half ? (x + this.speed) % half : 0;
        track.style.transform = `translate3d(${-x}px,0,0)`;
        requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    }

    /* -- flèches, onglets, puces ------------------------------------------- */
    bindControls() {
      const scope =
        this.root.closest('.swiper-container, [class*="slider"]') ||
        this.root.parentElement ||
        this.root;

      const prev = $('.swiper-click-zone--previous', scope) ||
                   $('.swiper-button-prev', scope) ||
                   $('[class*="prev"]', scope);
      const next = $('.swiper-click-zone--next', scope) ||
                   $('.swiper-button-next', scope) ||
                   $('[class*="next"]', scope);
      if (prev) prev.addEventListener('click', () => this.go(this.index - 1));
      if (next) next.addEventListener('click', () => this.go(this.index + 1));

      this.tabs = $$('[data-slider-nav-item]', scope);
      if (!this.tabs.length) this.tabs = $$('[role="tab"]', scope);
      this.tabs.forEach((tab, i) => {
        const t = parseInt(tab.dataset.index, 10);
        tab.addEventListener('click', () => this.go(Number.isNaN(t) ? i : t));
        tab.addEventListener('keydown', e => {
          if (e.key === 'ArrowRight') { e.preventDefault(); this.go(this.index + 1); }
          if (e.key === 'ArrowLeft')  { e.preventDefault(); this.go(this.index - 1); }
        });
      });

      this.bullets = $$('.swiper-pagination-bullet', scope);
      this.bullets.forEach((b, i) => b.addEventListener('click', () => this.go(i)));
    }

    bindSwipe() {
      let x0 = null;
      this.root.addEventListener('pointerdown', e => { x0 = e.clientX; });
      this.root.addEventListener('pointerup', e => {
        if (x0 === null) return;
        const dx = e.clientX - x0;
        if (Math.abs(dx) > 45) this.go(this.index + (dx < 0 ? 1 : -1));
        x0 = null;
      });
    }

    go(i, animate = true) {
      const max = this.slides.length - 1;
      this.index = i < 0 ? max : i > max ? 0 : i;
      this.wrapper.style.transitionDuration = (animate ? this.speed : 0) + 'ms';

      if (this.mode === 'fade') {
        this.slides.forEach((s, k) => {
          s.style.transition = `opacity ${this.speed}ms ease`;
          s.style.opacity = k === this.index ? '1' : '0';
          s.style.pointerEvents = k === this.index ? '' : 'none';
        });
      } else {
        // un carrousel qui montre plusieurs slides à la fois ne doit pas
        // défiler au-delà de son bord droit, sinon il finit sur du vide
        let off = this.slides[this.index].offsetLeft - this.slides[0].offsetLeft;
        const max = this.wrapper.scrollWidth - this.root.clientWidth;
        if (max > 0) off = Math.min(off, max);
        this.wrapper.style.transform = `translate3d(${-Math.max(0, off)}px,0,0)`;
      }

      this.slides.forEach((s, k) => {
        s.classList.toggle('swiper-slide-active', k === this.index);
        s.classList.toggle('swiper-slide-prev',   k === this.index - 1);
        s.classList.toggle('swiper-slide-next',   k === this.index + 1);
      });

      (this.tabs || []).forEach((t, k) => {
        const on = k === this.index;
        t.classList.toggle('active', on);
        t.setAttribute('aria-selected', on ? 'true' : 'false');
        t.tabIndex = on ? 0 : -1;
      });
      (this.bullets || []).forEach((b, k) =>
        b.classList.toggle('swiper-pagination-bullet-active', k === this.index));

      this.linked.forEach(s => { if (s.index !== this.index) s.go(this.index, animate); });
    }
  }

  /* ============================================ DÉTECTION DES COMPOSANTS === */

  const instances = new Map();

  /** Déduit le mode d'un slider à partir de ses classes. */
  function guessMode(root) {
    const c = (root.className || '').toLowerCase();
    if (/fade/.test(c)) return 'fade';
    if (/loop|marquee|ticker|defil|infinite/.test(c)) return 'marquee';
    return 'slide';
  }

  // 1. sliders déclarés dans CONFIG
  Object.entries(CONFIG.sliders).forEach(([sel, opts]) => {
    $$(sel).forEach(root => {
      if (!instances.has(root)) instances.set(root, new Slider(root, opts));
    });
  });

  // 2. tout autre .swiper non encore traité
  $$('.swiper, [class*="swiper-container"]').forEach(root => {
    if (instances.has(root)) return;
    if ($$('.swiper', root).length) return;       // conteneur parent, on ignore
    instances.set(root, new Slider(root, { mode: guessMode(root) }));
  });

  // 3. synchronisation des paires déclarées
  CONFIG.sync.forEach(([a, b]) => {
    const A = instances.get($(a)), B = instances.get($(b));
    if (A && B && A.ok && B.ok && A.slides.length === B.slides.length) {
      A.linked.push(B);
      B.linked.push(A);
    }
  });

  /* ========================================== LIRE LA SUITE / COLLAPSE ===== */

  $$('[data-collapse-text][data-container]').forEach(btn => {
    const scope  = btn.closest('.ti-inner, .review, article') || btn.parentElement;
    const target = $(btn.dataset.container, scope);
    if (!target) return;

    const labelOpen  = btn.dataset.openText     || 'Lire la suite';
    const labelClose = btn.dataset.collapseText || 'Cacher';
    const initial    = btn.dataset.initialHeight;

    if (initial) {
      target.style.maxHeight = initial + 'px';
      target.style.overflow  = 'hidden';
    }
    target.style.transition = 'max-height .3s ease';

    btn.setAttribute('role', 'button');
    btn.setAttribute('tabindex', '0');
    btn.setAttribute('aria-expanded', 'false');
    btn.textContent = labelOpen;

    const toggle = () => {
      const open = btn.getAttribute('aria-expanded') === 'true';
      btn.setAttribute('aria-expanded', open ? 'false' : 'true');
      btn.textContent = open ? labelOpen : labelClose;
      target.style.maxHeight = open
        ? (initial ? initial + 'px' : '0px')
        : target.scrollHeight + 'px';
    };

    btn.addEventListener('click', toggle);
    btn.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
    });
  });

  /* =============================================== ACCORDÉONS GÉNÉRIQUES === */
  /* Tout élément portant aria-expanded + aria-controls, sans <details>.       */

  $$('[aria-expanded][aria-controls]').forEach(btn => {
    const panel = document.getElementById(btn.getAttribute('aria-controls'));
    if (!panel || btn.dataset.collapseText) return;
    btn.addEventListener('click', () => {
      const open = btn.getAttribute('aria-expanded') === 'true';
      btn.setAttribute('aria-expanded', open ? 'false' : 'true');
      panel.hidden = open;
      panel.classList.toggle('is-open', !open);
    });
  });

  /* ======================================= MENU MOBILE ET SOUS-MENUS ======= */

  // bouton hamburger des thèmes WordPress à blocs
  const openBtn  = $('.wp-block-navigation__responsive-container-open');
  const closeBtn = $('.wp-block-navigation__responsive-container-close');
  const overlay  = $('.wp-block-navigation__responsive-container');
  if (openBtn && overlay) {
    const setOpen = on => {
      overlay.classList.toggle('is-menu-open', on);
      overlay.classList.toggle('has-modal-open', on);
      document.documentElement.classList.toggle('has-modal-open', on);
      openBtn.setAttribute('aria-expanded', on ? 'true' : 'false');
    };
    openBtn.addEventListener('click', () => setOpen(true));
    if (closeBtn) closeBtn.addEventListener('click', () => setOpen(false));
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') setOpen(false);
    });
  }

  // sous-menus : le survol est géré en CSS, on ajoute le clavier
  $$('li.has-child, .menu-item-has-children').forEach(li => {
    if (!$('.wp-block-navigation__submenu-container, .sub-menu', li)) return;
    li.addEventListener('focusin', () => li.classList.add('is-open'));
    li.addEventListener('focusout', e => {
      if (!li.contains(e.relatedTarget)) li.classList.remove('is-open');
    });
  });

  /* ============================================ ANIMATIONS AU SCROLL ====== */

  const animated = $$('.animup, .animate, .animdown, [data-anim]');
  if (animated.length && 'IntersectionObserver' in window && !reduced()) {
    const io = new IntersectionObserver(entries => {
      entries.forEach(e => {
        if (!e.isIntersecting) return;
        e.target.classList.add('is-visible', 'animated', 'in-view');
        io.unobserve(e.target);
      });
    }, { threshold: 0.15 });
    animated.forEach(el => io.observe(el));
  } else {
    animated.forEach(el => el.classList.add('is-visible', 'animated', 'in-view'));
  }

  /* ======================================================================== */
  /* ===================== MODULES SPÉCIFIQUES À AURLANE ==================== */
  /* ------------------------------------------------------------------------
     Tout ce qui précède est le moteur générique du pipeline. Ce qui suit tient
     aux noms de classes du thème Aurlane : à réécrire si la cible change.
     ---------------------------------------------------------------------- */

  const aurlane = { hamburger: false, megaImages: 0, instagram: 0, videos: 0 };

  /* -- 1. rendre au JS les noeuds que SingleFile avait marqués masqués ------
     SingleFile pose .sf-hidden sur tout ce qui n'était pas affiché à l'instant
     de la capture, avec display:none!important. On retire la classe sur les
     seuls noeuds dont on réanime le comportement, et uniquement sur ceux que
     le CSS du site masque déjà tout seul au repos : le rendu au repos ne bouge
     donc pas d'un pixel.
       - #js-hamburger            .hamburger{display:none} hors media mobile
       - .mega-menu-link-image    .mega-menu-link-image{display:none} sans .active
  */
  const unhide = el => el && el.classList.remove('sf-hidden');
  unhide($('#js-hamburger'));
  $$('img.mega-menu-link-image').forEach(unhide);

  /* SingleFile ne se contente pas de masquer : il vide aussi les descendants
     d'un élément masqué, et purge les règles CSS devenues inutilisées. Le
     bouton burger revient donc vide et sans style de barres. On le reconstruit
     à l'identique de la production — trois <span class="hamburger__bar"> et la
     règle telle qu'elle figure dans aurlane-combined.css.                     */
  const burgerBtn = $('#js-hamburger');
  if (burgerBtn && !burgerBtn.children.length) {
    for (let i = 0; i < 3; i++) {
      const bar = document.createElement('span');
      bar.className = 'hamburger__bar';
      burgerBtn.appendChild(bar);
    }
    const css = document.createElement('style');
    css.textContent =
      '.hamburger__bar{background:#333;display:block;height:1px;margin:3px auto;width:20px}';
    document.head.appendChild(css);
  }

  /* -- 2. menu mobile ------------------------------------------------------
     Le CSS ne définit aucun état ouvert : .mobile-menu est en
     pointer-events:none et .mobile-menu__inner en translateX(-100%). L'ouverture
     passait donc par du style inline posé en JS, que voici.                  */
  const burger  = $('#js-hamburger');
  const mMenu   = $('#mobile-menu');
  if (burger && mMenu) {
    const inner    = $('.mobile-menu__inner', mMenu);
    const backdrop = $('.mobile-menu__backdrop', mMenu);
    if (backdrop) {
      backdrop.style.background = 'rgba(0,0,0,.4)';
      backdrop.style.transition = 'opacity .3s ease';
      backdrop.style.border = '0';
    }

    const setOpen = on => {
      mMenu.style.pointerEvents = on ? 'auto' : 'none';
      if (inner)    inner.style.transform = on ? 'translateX(0)' : '';
      if (backdrop) backdrop.style.opacity = on ? '1' : '0';
      burger.setAttribute('aria-expanded', on ? 'true' : 'false');
      document.documentElement.style.overflow = on ? 'hidden' : '';
    };

    burger.addEventListener('click', () => setOpen(true));
    $('#js-mobile-menu-close', mMenu)?.addEventListener('click', () => setOpen(false));
    backdrop?.addEventListener('click', () => setOpen(false));
    document.addEventListener('keydown', e => { if (e.key === 'Escape') setOpen(false); });
    setOpen(false);
    aurlane.hamburger = true;

    /* sous-menus dépliants : .sub-menu est en max-height:0 avec une transition,
       le parent n'a pas de bouton dédié — c'est le lien lui-même qui déplie.
       Chaque catégorie reste atteignable par l'entrée « Toutes les… » du
       sous-menu, donc on peut intercepter le clic sans perdre de destination. */
    $$('.mobile-menu-main li.menu-item-has-children', mMenu).forEach(li => {
      const link = li.querySelector(':scope > a');
      const sub  = li.querySelector(':scope > ul.sub-menu');
      if (!link || !sub) return;
      link.setAttribute('aria-expanded', 'false');
      link.addEventListener('click', e => {
        e.preventDefault();
        const open = link.getAttribute('aria-expanded') === 'true';
        link.setAttribute('aria-expanded', open ? 'false' : 'true');
        li.classList.toggle('is-open', !open);
        sub.style.maxHeight = open ? '0px' : sub.scrollHeight + 'px';
      });
    });
  }

  /* -- 3. mega-menu : image qui suit le lien survolé -----------------------
     Chaque lien porte data-item-id, chaque image porte le même. Le CSS ne
     connaît que .mega-menu-link-image.active — reste à déplacer la classe.   */
  $$('.mega').forEach(mega => {
    const images = $$('.mega-menu-link-image', mega);
    if (images.length < 2) return;
    const byId = new Map(images.map(i => [i.dataset.itemId, i]));
    const initial = images.find(i => i.classList.contains('active')) || images[0];

    const show = img => {
      if (!img) return;
      images.forEach(i => i.classList.toggle('active', i === img));
      aurlane.megaImages++;
    };

    $$('.mega-menu-links > li > a[data-item-id]', mega).forEach(a => {
      const img = byId.get(a.dataset.itemId);
      if (!img) return;                     // lien sans visuel associé
      a.addEventListener('mouseenter', () => show(img));
      a.addEventListener('focus', () => show(img));
    });
    mega.addEventListener('mouseleave', () => show(initial));
  });

  // aria-expanded des entrées de menu à mega : le survol est en CSS
  // (:hover, :focus-within), on ne synchronise que l'état annoncé.
  $$('li.has-mega').forEach(li => {
    const link = li.querySelector(':scope > a[aria-expanded]');
    if (!link) return;
    const set = on => link.setAttribute('aria-expanded', on ? 'true' : 'false');
    li.addEventListener('mouseenter', () => set(true));
    li.addEventListener('mouseleave', () => set(false));
    li.addEventListener('focusin',  () => set(true));
    li.addEventListener('focusout', e => {
      if (!li.contains(e.relatedTarget)) set(false);
    });
  });

  /* -- 4. carrousel Instagram (Owl Carousel de Smash Balloon) --------------
     Rail de 36 éléments : 9 clones, 18 réels, 9 clones. La pagination compte
     3 puces, soit 6 éléments par page. On ne pose surtout PAS de classe
     .swiper-slide ici : le CSS de Swiper est présent dans style.css et son
     .swiper-slide{width:100%} écraserait la largeur de 240 px des éléments.  */
  const owl = $('#sbi_images.sbi_carousel') || $('.sbi_carousel');
  if (owl) {
    const stage = $('.sbi-owl-stage', owl);
    const items = $$('.sbi-owl-item', owl);
    const dots  = $$('.sbi-owl-dots .sbi-owl-dot', owl);
    const real  = items.filter(i => !i.classList.contains('cloned'));

    if (stage && real.length > 1) {
      const pages    = Math.max(dots.length, 1);
      const pageSize = Math.max(1, Math.round(real.length / pages));
      let page = 0;

      const go = p => {
        page = (p + pages) % pages;
        const anchor = real[Math.min(page * pageSize, real.length - 1)];
        stage.style.transition = 'transform .4s ease';
        stage.style.transform  = `translate3d(${-anchor.offsetLeft}px,0,0)`;
        dots.forEach((d, k) => d.classList.toggle('active', k === page));
      };

      $('.sbi-owl-prev', owl)?.addEventListener('click', () => go(page - 1));
      $('.sbi-owl-next', owl)?.addEventListener('click', () => go(page + 1));
      dots.forEach((d, k) => d.addEventListener('click', () => go(k)));
      go(0);
      aurlane.instagram = real.length;
    }
  }

  /* -- 5. vidéos de bannière ----------------------------------------------
     Les <source> ont été recâblés sur des fichiers locaux par
     tools/fetch_missing.py. L'attribut muted seul ne suffit pas toujours à
     obtenir la lecture automatique : il faut aussi la propriété.             */
  $$('video[autoplay]').forEach(v => {
    v.muted = true;
    v.playsInline = true;
    const kick = () => v.play().catch(() => {});
    kick();
    v.addEventListener('loadeddata', kick, { once: true });
    aurlane.videos++;
  });

  /* ================================================== DIAGNOSTIC ========== */
  /* window.__clone.report() dans la console : liste ce qui a été réanimé.    */

  window.__clone = {
    sliders: instances,
    report() {
      const rows = [];
      instances.forEach((s, root) => rows.push({
        selecteur: '.' + (root.className || '').split(' ').filter(Boolean)[0],
        mode: s.mode || 'inactif',
        slides: s.slides ? s.slides.length : 0,
        onglets: s.tabs ? s.tabs.length : 0,
      }));
      console.table(rows);
      console.log('collapse :', $$('[data-collapse-text]').length);
      console.log('animés   :', animated.length);
      console.log('aurlane  :', {
        'menu mobile':        aurlane.hamburger,
        'mega-menus câblés':  $$('.mega').length,
        'items Instagram':    aurlane.instagram,
        'vidéos relancées':   aurlane.videos,
      });
      return rows;
    },
  };
})();
