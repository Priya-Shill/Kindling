/* =========================================================
   INFERENCE — real radar & empty state handling
   ========================================================= */

(() => {

    const K = window.Kindling;
    const { $, $$, el, esc, colorOf, addGlow, drawNode, onActivate } = K;

    const inf = $('#inferenceMap');
    const C = { x: 320, y: 262 }, R = 170;

    let scores = {};
    const N = K.patterns.length;

    const pt = (i, r) => { const a = -Math.PI / 2 + i * 2 * Math.PI / N; return { x: C.x + Math.cos(a) * r, y: C.y + Math.sin(a) * r, c: Math.cos(a), s: Math.sin(a) }; };

    const evList = $('#evidenceList'), infFoot = $('#infFoot');
    const infGrid = $('#inferenceGrid'), infSide = $('#inferenceSide');

    // Fullscreen-only: the evidence panel is hidden by default and
    // slides in over the chart when a star is picked - same pattern
    // as Career Graph's fsPanelOpen, independent of `currentTheme` so
    // entering fullscreen always starts closed.
    let fsPanelOpen = false;
    function setFsPanelOpen(open) {
        fsPanelOpen = open;
        infSide.classList.toggle('is-open', open);
    }

    function getStrengthLabel(value) {
        if (typeof value !== 'number') return 'No data yet';
        if (value >= 0.75) return 'Showing up often';
        if (value >= 0.5) return 'Showing up';
        if (value >= 0.25) return 'Starting to appear';
        return 'Not yet showing';
    }

    let infEls = {}, axisEls = {}, youNode = null, currentTheme = null;

    function renderRadar() {
        inf.innerHTML = '';

        const defs = el('defs', {}, inf);
        const infGlow = addGlow(inf);

        const rg = el('radialGradient', { id: 'radarFill', cx: '50%', cy: '50%', r: '60%' }, defs);
        el('stop', { offset: '0', 'stop-color': '#f5c46a', 'stop-opacity': '0.38' }, rg);
        el('stop', { offset: '1', 'stop-color': '#e8a94a', 'stop-opacity': '0.10' }, rg);

        const grid = el('g', {}, inf);
        [0.25, 0.5, 0.75, 1].forEach(f => el('polygon', { class: 'radar-ring', points: K.patterns.map((_, i) => { const p = pt(i, R * f); return `${p.x},${p.y}`; }).join(' ') }, grid));

        axisEls = {};
        K.patterns.forEach((t, i) => { const p = pt(i, R); axisEls[t.id] = el('line', { class: 'radar-axis', x1: C.x, y1: C.y, x2: p.x, y2: p.y }, grid); });

        const shapePts = K.patterns.map((t, i) => { const reach = scores[t.key] || 0; const p = pt(i, R * reach); return `${p.x},${p.y}`; }).join(' ');
        el('polygon', { class: 'radar-glow', points: shapePts }, inf);
        el('polygon', { class: 'radar-shape', points: shapePts }, inf);

        const infNodes = el('g', { class: 'radar-vertices' }, inf);
        infEls = {};

        K.patterns.forEach((t, i) => {
            const reach = scores[t.key] || 0;
            const v = pt(i, R * reach), tip = pt(i, R + 24);
            const anchor = tip.c > 0.3 ? 'start' : tip.c < -0.3 ? 'end' : 'middle';
            const g = drawNode(infNodes, { ...v }, infGlow, {
                label: t.label, core: 4.5, halo: 16, anchor,
                lx: tip.x - v.x, ly: tip.y - v.y + (tip.s < -0.5 ? -2 : tip.s > 0.5 ? 12 : 5)
            });
            g.querySelector('circle:nth-of-type(2)').setAttribute('fill', colorOf[t.tone]);
            g.querySelectorAll('circle')[3].setAttribute('fill', colorOf[t.tone]);
            infEls[t.id] = g;
            onActivate(g, () => selectTheme(t.id, true));
        });

        youNode = drawNode(infNodes, { ...C, tone: 'warm' }, infGlow, { label: 'You', core: 3.5, halo: 12, lx: 0, ly: 20, anchor: 'middle' });
        youNode.setAttribute('aria-label', 'You, show everything');
        onActivate(youNode, () => selectTheme(null));

        requestAnimationFrame(() => inf.classList.add('is-shown'));
    }

    function renderEvidence() {
        evList.innerHTML = K.patterns.map(t => {
            const c = colorOf[t.tone];
            return `<li><button class="evidence" data-theme="${t.id}">
        ${esc(t.description)}
        <span class="evidence-meta"><span class="theme-tag"><i style="background:${c};box-shadow:0 0 6px ${c}"></i>${esc(t.label)}</span><span>${esc(getStrengthLabel(scores[t.key]))}</span></span>
      </button></li>`;
        }).join('');
    }

    function renderFoot(id) {
        if (!id) {
            infFoot.innerHTML = '<span>Select a star to see the pattern it represents.</span>';
            return;
        }
        const t = K.patternById[id], c = colorOf[t.tone];
        const v = K.feelings[id];
        infFoot.innerHTML = `<strong><i style="background:${c};box-shadow:0 0 8px ${c}"></i>${esc(t.label)}</strong>
      <span class="feel"><span>Does this feel like you?</span>
        <button class="btn-line" data-feel="yes" aria-pressed="${v === 'yes'}">Feels right</button>
        <button class="btn-line" data-feel="no" aria-pressed="${v === 'no'}">Not quite</button></span>`;
    }

    function selectTheme(id, fromMap) {
        currentTheme = id || null;
        Object.entries(infEls).forEach(([k, g]) => g.classList.toggle('is-selected', k === id));
        Object.entries(axisEls).forEach(([k, a]) => a.classList.toggle('is-lit', k === id));
        youNode?.classList.toggle('is-selected', !id);
        evList.classList.toggle('is-filtered', !!id);
        let first = null;
        $$('.evidence', evList).forEach(b => { const on = b.dataset.theme === id; b.classList.toggle('is-lit', on); if (on && !first) first = b; });
        if (fromMap && first) first.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        renderFoot(currentTheme);

        if (id) {
            if (infGrid.classList.contains('is-fullscreen')) setFsPanelOpen(true);
        } else {
            setFsPanelOpen(false);
        }
    }

    evList.addEventListener('click', e => { const b = e.target.closest('.evidence'); if (b) selectTheme(b.dataset.theme === currentTheme ? null : b.dataset.theme); });
    infFoot.addEventListener('click', e => {
        const f = e.target.closest('[data-feel]');
        if (f && currentTheme) K.setFeeling(currentTheme, f.dataset.feel);
    });

    K.onFeelingChange.push((traitKey) => {
        if (currentTheme === traitKey) renderFoot(traitKey);
    });

    // Clean Empty State when scores are 0 / missing / weak
    function showEmptyState(message) {
        scores = {};
        if (inf) {
            inf.innerHTML = `
                <g transform="translate(320, 230)">
                    <text text-anchor="middle" fill="#f5c46a" font-size="18" font-weight="600">✨ Patterns Waiting to Emerge</text>
                    <text text-anchor="middle" fill="#a0aec0" font-size="13" y="32">Share details in Explore chat to unlock your pattern map</text>
                </g>
            `;
            inf.classList.add('is-shown');
        }

        if (evList) {
            evList.innerHTML = `
                <li class="note-card glass" style="padding:22px; border-left:3px solid #f5c46a; margin-top:12px;">
                    <p style="color:#fff; font-weight:600; font-size:1rem; margin-bottom:8px;">Need a little more detail</p>
                    <p style="color:#a0aec0; font-size:0.85rem; line-height:1.5; margin-bottom:16px;">${esc(message)}</p>
                    <a href="#explore" class="btn-gold sm" style="display:inline-block; text-decoration:none; font-size:0.8rem;">
                        Go to Explore Chat →
                    </a>
                </li>
            `;
        }

        if (infFoot) {
            infFoot.innerHTML = '<span>Complete a real conversation in Explore to see your pattern map.</span>';
        }
    }

    async function loadInference() {
        const combined = K.isConnectThreadsOn();
        const sessionId = K.getResultsSessionId();

        if (!sessionId) {
            showEmptyState("Start a conversation on Explore first to reveal your pattern map.");
            return;
        }

        try {
            const scopeParam = combined ? '&scope=all' : '';
            const response = await fetch(`${K.API_BASE_URL}/api/chat/inference/${sessionId}?token=${encodeURIComponent(K.getAuthToken())}${scopeParam}`);

            if (response.status === 404) {
                const body = await response.json().catch(() => null);
                showEmptyState(body?.detail || "We need a little more to go on! Share a few real details about your hobbies or interests in Explore.");
                return;
            }

            if (!response.ok) throw new Error(`Server returned ${response.status}`);

            const data = await response.json();

            if (data.inference_failed) {
                showEmptyState("Scoring did not complete cleanly for this session. Keep exploring and check back.");
                return;
            }

            scores = data.inference || {};

            // CHECK: Is there any real signal? (Highest score must be at least 0.15)
            const maxScore = Math.max(...Object.values(scores).map(v => Number(v) || 0));
            if (maxScore < 0.15) {
                showEmptyState("We haven't detected strong interest patterns yet. Tell Kindling about a hobby, project, or activity you enjoy in Explore!");
                return;
            }

            // Real signal exists — render radar and evidence list!
            renderRadar();
            renderEvidence();
            renderFoot(null);

        } catch (error) {
            console.error('Failed to load inference:', error);
            showEmptyState("We could not reach the server. Please try again.");
        }
    }

    function refreshScopeBar() {
        K.renderScopeBar($('#inferenceScopeBar'), loadInference);
    }

    // ── Fullscreen ───────────────────────────────────────────
    // Same pattern as Career Graph's: fullscreens #inferenceGrid so
    // the evidence panel can overlay the chart instead of only the
    // fullscreened subtree; restored either way (button, Escape, or
    // browser chrome all fire fullscreenchange).
    const infFsBtn = $('#infFullscreen');
    const requestInfFs = el => (el.requestFullscreen || el.webkitRequestFullscreen)?.call(el);
    const exitInfFs = () => (document.exitFullscreen || document.webkitExitFullscreen)?.call(document);
    const infFsElement = () => document.fullscreenElement || document.webkitFullscreenElement;
    const infFsSupported = !!(infGrid.requestFullscreen || infGrid.webkitRequestFullscreen);

    const EXPAND_ICON = '<path d="M1 1l4.5 4.5M13 13l-4.5-4.5" stroke="currentColor" stroke-width="1.3" fill="none" stroke-linecap="round"/><path d="M1 5V1h4M13 9v4H9" stroke="currentColor" stroke-width="1.3" fill="none" stroke-linecap="round" stroke-linejoin="round"/>';
    const COLLAPSE_ICON = '<path d="M5.5 5.5 1 1M8.5 8.5 13 13" stroke="currentColor" stroke-width="1.3" fill="none" stroke-linecap="round"/><path d="M5 1v4H1M9 13v-4h4" stroke="currentColor" stroke-width="1.3" fill="none" stroke-linecap="round" stroke-linejoin="round"/>';

    if (infFsBtn) {
        infFsBtn.hidden = !infFsSupported;
        if (infFsSupported) {
            infFsBtn.addEventListener('click', () => {
                if (infFsElement() === infGrid) exitInfFs(); else requestInfFs(infGrid);
            });
            const syncInfFullscreenState = () => {
                const active = infFsElement() === infGrid;
                infGrid.classList.toggle('is-fullscreen', active);
                infFsBtn.setAttribute('aria-pressed', String(active));
                const label = active ? 'Exit full screen' : 'Full screen';
                infFsBtn.setAttribute('aria-label', label);
                infFsBtn.setAttribute('title', label);
                const svg = infFsBtn.querySelector('svg');
                if (svg) svg.innerHTML = active ? COLLAPSE_ICON : EXPAND_ICON;

                // Hidden by default on entering fullscreen (even if a
                // star was already selected before), and cleaned up
                // when leaving - Esc closes fullscreen itself but was
                // never meant to be relied on to close the panel too.
                setFsPanelOpen(false);
            };
            document.addEventListener('fullscreenchange', syncInfFullscreenState);
            document.addEventListener('webkitfullscreenchange', syncInfFullscreenState);
        }
    }

    $('#infPanelClose')?.addEventListener('click', () => setFsPanelOpen(false));

    // Fullscreen only: clicking empty chart space (not a star node or
    // the toolbar) dismisses the slide-over panel without touching
    // the underlying selection.
    $('#inferenceCard')?.addEventListener('click', e => {
        if (!fsPanelOpen || !infGrid.classList.contains('is-fullscreen')) return;
        if (e.target.closest('.inf-tools, .node')) return;
        setFsPanelOpen(false);
    });

    K.onRoute.inference = () => {
        refreshScopeBar();
        loadInference();
    };

    // Connect Threads toggled, or a different thread picked in the
    // scope bar - refetch this page's own data without a reload.
    window.addEventListener('kindling:scope-change', () => {
        if (document.body.dataset.page !== 'inference') return;
        refreshScopeBar();
        loadInference();
    });

})();