/* =========================================================
   SHARED HELPERS + NODE DRAWING
   Used by inference.js and career-graph.js. Kept from the
   mockup: node size/glow are purely visual — no number is
   ever printed anywhere a node is drawn.
   ========================================================= */

(() => {

    const K = window.Kindling;
    const { $ } = K;
    const svgNS = 'http://www.w3.org/2000/svg';

    K.el = (tag, attrs = {}, parent) => {
        const n = document.createElementNS(svgNS, tag);
        for (const k in attrs) n.setAttribute(k, attrs[k]);
        if (parent) parent.appendChild(n);
        return n;
    };

    K.lc = s => s.split(' ').map(w => /^[A-Z]{2}/.test(w) ? w : w.toLowerCase()).join(' ');

    K.esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

    /*
     * Small, dependency-free markdown-ish renderer for Kindling chat
     * replies. Escapes HTML FIRST, then only ever introduces tags via
     * these fixed regexes over the already-escaped text — so no user-
     * or LLM-supplied text can ever inject real HTML (there's no way
     * for escaped input to end up containing '<' or '>' again). Only
     * supports bold, italics, inline code, and bullet/numbered lists,
     * since that's all real chat replies use.
     */
    K.renderMarkdown = function renderMarkdown(raw) {
        const inline = s => s
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
            .replace(/\*([^*]+)\*/g, '<em>$1</em>')
            .replace(/_([^_]+)_/g, '<em>$1</em>');

        const blocks = K.esc(raw).split(/\n{2,}/);
        return blocks.map(block => {
            const lines = block.split('\n').filter(l => l.trim().length);
            if (!lines.length) return '';
            if (lines.every(l => /^[-*]\s+/.test(l))) {
                return '<ul>' + lines.map(l => `<li>${inline(l.replace(/^[-*]\s+/, ''))}</li>`).join('') + '</ul>';
            }
            if (lines.every(l => /^\d+\.\s+/.test(l))) {
                return '<ol>' + lines.map(l => `<li>${inline(l.replace(/^\d+\.\s+/, ''))}</li>`).join('') + '</ol>';
            }
            return `<p>${lines.map(inline).join('<br>')}</p>`;
        }).join('');
    };

    K.toast = function toast(msg) {
        const t = $('#toast'); t.textContent = msg; t.classList.add('is-shown');
        clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove('is-shown'), 2200);
    };

    K.colorOf = {
        warm: 'var(--warm)', cool: 'var(--cool)', pale: 'var(--cool-soft)', violet: 'var(--violet)',
        hub: 'var(--cool-soft)', area: 'var(--violet)', related: 'var(--warm-soft)', direction: 'var(--amber)',
        // Real Career Graph tree node types (backend/career_tree.py):
        // field reuses "related"'s cream tone, career reuses "direction"'s amber.
        field: 'var(--warm-soft)', career: 'var(--amber)'
    };

    K.addGlow = function addGlow(svg, dev = 6) {
        let defs = svg.querySelector('defs') || svg.insertBefore(K.el('defs'), svg.firstChild);
        const f = K.el('filter', { id: svg.id + '-glow', x: '-150%', y: '-150%', width: '400%', height: '400%' }, defs);
        K.el('feGaussianBlur', { stdDeviation: dev }, f);
        return `url(#${svg.id}-glow)`;
    };

    K.drawNode = function drawNode(parent, n, glow, { core = 4.5, halo = 14, label = n.label, lx, ly, anchor = 'start', cls = '' } = {}) {
        const g = K.el('g', { class: 'node ' + cls, tabindex: '0', role: 'button', 'aria-label': label, transform: `translate(${n.x} ${n.y})` }, parent);
        const c = K.colorOf[n.tone || n.type];
        K.el('circle', { r: Math.max(core + 12, 14), fill: 'transparent' }, g);
        K.el('circle', { class: 'halo', r: halo, fill: c, filter: glow }, g);
        K.el('circle', { class: 'ring', r: core + 6 }, g);
        K.el('circle', { r: core, fill: c }, g);
        K.el('circle', { r: core * 0.45, fill: '#fffaf0', opacity: 0.9 }, g);
        const t = K.el('text', { x: lx ?? core + 11, y: ly ?? 5, 'text-anchor': anchor }, g);
        t.textContent = label;
        return g;
    };

    K.onActivate = function onActivate(g, fn) {
        g.addEventListener('click', fn);
        g.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fn(); } });
    };

    /*
     * Shared fullscreen behavior for Career Graph and Inference - one
     * implementation so the two can't drift apart, and so the shared
     * starfield (#sky/.nebula) can't be fought over by two independent
     * fullscreenchange listeners each reparenting it. Only the
     * container that IS fullscreen right now claims the starfield;
     * it's only handed back to <body> once nothing at all is
     * fullscreen, so one screen's fullscreenchange handler can never
     * yank the starfield away from a *different* screen that just
     * entered fullscreen in the same event tick.
     */
    const FS_EXPAND_ICON = '<path d="M1 1l4.5 4.5M13 13l-4.5-4.5" stroke="currentColor" stroke-width="1.3" fill="none" stroke-linecap="round"/><path d="M1 5V1h4M13 9v4H9" stroke="currentColor" stroke-width="1.3" fill="none" stroke-linecap="round" stroke-linejoin="round"/>';
    const FS_COLLAPSE_ICON = '<path d="M5.5 5.5 1 1M8.5 8.5 13 13" stroke="currentColor" stroke-width="1.3" fill="none" stroke-linecap="round"/><path d="M5 1v4H1M9 13v-4h4" stroke="currentColor" stroke-width="1.3" fill="none" stroke-linecap="round" stroke-linejoin="round"/>';

    K.setupFullscreen = function setupFullscreen({ container, button, onChange }) {
        const requestFs = el => (el.requestFullscreen || el.webkitRequestFullscreen)?.call(el);
        const exitFs = () => (document.exitFullscreen || document.webkitExitFullscreen)?.call(document);
        const fsElement = () => document.fullscreenElement || document.webkitFullscreenElement;
        const isActive = () => fsElement() === container;
        const supported = !!(container.requestFullscreen || container.webkitRequestFullscreen);

        if (!button) return { supported, isActive };
        button.hidden = !supported;
        if (!supported) return { supported, isActive: () => false };

        const sky = document.getElementById('sky'), nebula = $('.nebula');

        button.addEventListener('click', () => { isActive() ? exitFs() : requestFs(container); });

        const sync = () => {
            const active = isActive();
            container.classList.toggle('is-fullscreen', active);
            button.setAttribute('aria-pressed', String(active));
            const label = active ? 'Exit full screen' : 'Full screen';
            button.setAttribute('aria-label', label);
            button.setAttribute('title', label);
            const svg = button.querySelector('svg');
            if (svg) svg.innerHTML = active ? FS_COLLAPSE_ICON : FS_EXPAND_ICON;

            if (active) {
                if (sky) container.insertBefore(sky, container.firstChild);
                if (nebula) container.insertBefore(nebula, container.firstChild);
            } else if (!fsElement()) {
                if (sky && sky.parentElement !== document.body) document.body.insertBefore(sky, document.body.firstChild);
                if (nebula && nebula.parentElement !== document.body) document.body.insertBefore(nebula, document.body.firstChild);
            }

            onChange?.(active);
        };

        document.addEventListener('fullscreenchange', sync);
        document.addEventListener('webkitfullscreenchange', sync);

        return { supported, isActive };
    };

    /*
     * Navigating away (changing location.hash) while still fullscreen
     * left the browser showing the new page/route underneath the OS's
     * actual fullscreen chrome, instead of a normal windowed view -
     * exits fullscreen first, waits for that to actually finish, then
     * navigates. Safe to call when nothing is fullscreen (navigates
     * immediately, no-op wait).
     */
    K.exitFullscreenThenNavigate = function exitFullscreenThenNavigate(hash) {
        const fsElement = () => document.fullscreenElement || document.webkitFullscreenElement;
        if (!fsElement()) {
            location.hash = hash;
            return;
        }
        const onExit = () => {
            document.removeEventListener('fullscreenchange', onExit);
            document.removeEventListener('webkitfullscreenchange', onExit);
            location.hash = hash;
        };
        document.addEventListener('fullscreenchange', onExit);
        document.addEventListener('webkitfullscreenchange', onExit);
        (document.exitFullscreen || document.webkitExitFullscreen)?.call(document);
    };

    /*
     * Generic safety net for the same problem, for plain <a href="#x">
     * links rendered inside a fullscreen panel (e.g. Inference's empty-
     * state "Go to Explore Chat" link) rather than a JS-driven
     * location.hash assignment - those already call
     * K.exitFullscreenThenNavigate directly at their own call site.
     * Capture-phase so it runs before the browser's own native
     * navigation for the click.
     */
    /*
     * Shared refit helper: sets an SVG's viewBox to tightly fit its
     * own actually-rendered content (via getBBox, so it adapts to
     * whatever is really on screen - including a fullscreen-only
     * larger font bumping text wider than a viewBox sized only for
     * the normal-view font size would allow, which is exactly what
     * clipped Inference's edge labels in fullscreen: the viewBox
     * itself didn't contain the real geometry at the bigger font,
     * so the SVG's own implicit overflow:hidden clipped it - no
     * amount of the *container* resizing correctly could fix that,
     * since preserveAspectRatio="xMidYMid meet" (the default) always
     * shows the whole declared viewBox, but can't show content that
     * exceeds it. Re-run this after anything that can change the
     * rendered size of that content (a fresh render, or a fullscreen
     * class toggle that changes font-size via CSS).
     */
    K.fitSvgViewBox = function fitSvgViewBox(svg, padding = 20) {
        const box = svg.getBBox();
        if (!box.width || !box.height) return;
        svg.setAttribute('viewBox', `${box.x - padding} ${box.y - padding} ${box.width + padding * 2} ${box.height + padding * 2}`);
    };

    K.interceptFullscreenNavLinks = function interceptFullscreenNavLinks(panelEl) {
        panelEl.addEventListener('click', e => {
            const a = e.target.closest('a[href^="#"]');
            if (!a) return;
            const fsElement = document.fullscreenElement || document.webkitFullscreenElement;
            if (!fsElement) return;
            e.preventDefault();
            K.exitFullscreenThenNavigate(a.getAttribute('href').slice(1));
        }, true);
    };

})();
