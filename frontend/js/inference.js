/* =========================================================
   INFERENCE — real radar & empty state handling
   ========================================================= */

(() => {

    const K = window.Kindling;
    const { $, $$, el, esc, colorOf, addGlow, drawNode, onActivate } = K;

    const inf = $('#inferenceMap');
    // Enlarged from the original R:170 (with the viewBox in index.html
    // widened to match) so the radar fills more of its card - it used
    // to sit small with a lot of unused margin around it.
    const C = { x: 320, y: 262 }, R = 195;

    let scores = {};
    const N = K.patterns.length;

    const pt = (i, r) => { const a = -Math.PI / 2 + i * 2 * Math.PI / N; return { x: C.x + Math.cos(a) * r, y: C.y + Math.sin(a) * r, c: Math.cos(a), s: Math.sin(a) }; };

    const evList = $('#evidenceList'), infFoot = $('#infFoot');
    const infGrid = $('#inferenceGrid'), infSide = $('#inferenceSide'), infCard = $('#inferenceCard');
    K.interceptFullscreenNavLinks(infSide);

    // Fullscreen-only: the evidence panel is hidden by default and
    // slides in over the chart when a star is picked - same pattern
    // as Career Graph's fsPanelOpen, independent of `currentTheme` so
    // entering fullscreen always starts closed.
    let fsPanelOpen = false;
    function setFsPanelOpen(open) {
        fsPanelOpen = open;
        infSide.classList.toggle('is-open', open);
    }

    // Same real-evidence line backend/career_tree.py's own
    // EVIDENCE_THRESHOLD uses (that file's comment explicitly keys off
    // this one) - below it, a pattern isn't "evidence" yet, so it's
    // left off the list entirely rather than shown with a score-like
    // strength tag ("Not yet showing", "Starting to appear"...),
    // which read as a score by another name.
    const EVIDENCE_THRESHOLD = 0.25;

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

        // ly pushed further down than a proportional label offset would
        // be, since low-score axes place their own point/label right on
        // top of center - this keeps "You" legible under that crowding
        // rather than just scaling with the radar's own radius.
        youNode = drawNode(infNodes, { ...C, tone: 'warm' }, infGlow, { label: 'You', core: 3.5, halo: 12, lx: 0, ly: 32, anchor: 'middle' });
        youNode.setAttribute('aria-label', 'You, show everything');
        onActivate(youNode, () => selectTheme(null));

        // Fits the viewBox to what's actually drawn (see K.fitSvgViewBox
        // in nodes.js) - a fixed viewBox sized for the normal-view font
        // doesn't contain the larger fullscreen font's wider text, and
        // the SVG clips anything outside its own viewBox regardless of
        // how the container around it is sized. Re-run on every
        // fullscreen toggle too (see K.setupFullscreen below), since
        // that's exactly when the font-size - and so the real geometry
        // this needs to fit - changes.
        K.fitSvgViewBox(inf, 20);

        requestAnimationFrame(() => inf.classList.add('is-shown'));
    }

    function renderEvidence() {
        evList.innerHTML = K.patterns
            .filter(t => (scores[t.key] || 0) >= EVIDENCE_THRESHOLD)
            .map(t => {
                const c = colorOf[t.tone];
                return `<li><button class="evidence" data-theme="${t.id}">
        ${esc(t.description)}
        <span class="evidence-meta"><span class="theme-tag"><i style="background:${c};box-shadow:0 0 6px ${c}"></i>${esc(t.label)}</span></span>
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
    // Fullscreens #inferenceGrid (not just the chart) so the starfield
    // canvas, reparented into it for the duration by the shared
    // K.setupFullscreen helper, keeps drifting behind the radar.
    const infFsBtn = $('#infFullscreen');

    K.setupFullscreen({
        container: infGrid,
        button: infFsBtn,
        onChange: active => {
            // Hidden by default on entering fullscreen (even if a star
            // was already selected before), and cleaned up when
            // leaving - Esc closes fullscreen itself but was never
            // meant to be relied on to close the panel too.
            setFsPanelOpen(false);

            // The "Does this feel like you?" foot bar moves into the
            // slide-over panel for fullscreen (so a selected star's
            // feel buttons show alongside its evidence cards there)
            // and back to its normal spot under the chart on exit.
            if (active) infSide.appendChild(infFoot);
            else infCard.appendChild(infFoot);

            // The fullscreen class toggle (just applied above) changes
            // the axis label font-size via CSS - refit so the viewBox
            // contains the real geometry at whichever size is now
            // active, on the way in AND the way back out.
            requestAnimationFrame(() => K.fitSvgViewBox(inf, 20));
        }
    });

    $('#infPanelClose')?.addEventListener('click', () => setFsPanelOpen(false));

    // Fullscreen only: clicking empty chart space (not a star node or
    // the toolbar) dismisses the slide-over panel without touching
    // the underlying selection.
    infCard.addEventListener('click', e => {
        if (!fsPanelOpen || !infGrid.classList.contains('is-fullscreen')) return;
        if (e.target.closest('.graph-tools, .node')) return;
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