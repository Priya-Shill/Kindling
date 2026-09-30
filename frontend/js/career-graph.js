/* =========================================================
   CAREER GRAPH — real branching tree & empty state
   ========================================================= */

(() => {

    const K = window.Kindling;
    const { $, $$, el, esc, lc, colorOf, addGlow, drawNode, onActivate, toast } = K;

    const gsvg = $('#graphMap'), frame = $('#graphFrame');
    let layer = $('#graphLayer');
    const gGlow = addGlow(gsvg, 5);
    gsvg.setAttribute('viewBox', '-540 -480 1080 960');

    const panel = $('#graphPanel');
    const panelContent = $('#graphPanelContent');

    // Fullscreen-only: the info panel is hidden by default and slides
    // in over the graph when a node is picked - fsPanelOpen tracks
    // that independently of `selected` so entering fullscreen always
    // starts closed, even if a node was already selected beforehand.
    let fsPanelOpen = false;
    function setFsPanelOpen(open) {
        fsPanelOpen = open;
        panel.classList.toggle('is-open', open);
    }

    let treeNodes = [], treeEdges = [];
    let byId = {};
    let childrenOf = {};
    let neighbors = {};
    let nodeEls = {};
    let edgeEls = [];
    let selected = null;
    let opened = new Set();
    let graphFilter = 'all';

    const AREA_R = 175, FIELD_R = 265, CAREER_R = 350;

    function mapLabel(label) {
        return label && label.length > 22 ? label.slice(0, 21).trimEnd() + '…' : label;
    }

    const kindName = {
        hub: 'Center of your exploration', area: 'Area of interest',
        field: 'Related field', career: 'Possible direction'
    };
    const branchSectionLabel = {
        hub: 'Areas branching from here', area: 'Fields branching from here', field: 'Careers branching from here'
    };
    const LETTER_TO_AXIS = {
        R: 'builds_tinkers', I: 'investigates_why', A: 'creates_expresses',
        S: 'works_with_people', E: 'leads_persuades', C: 'organizes_systems'
    };

    // Connect Threads' first combined-mode build re-scores every real
    // thread and runs full AI enrichment on every node, none of it
    // cached yet - that first request can take 60-100+ seconds on a
    // cold backend. Every request after it hits the cache and is
    // instant, same as single-session loads already are - this is
    // shown once per account, not on every combined-mode visit.
    function renderLoadingCombined() {
        if (layer) {
            try {
                layer.innerHTML = `
                    <text text-anchor="middle" x="0" y="-10" fill="#f5c46a" font-size="20" font-weight="600">Building your combined career map</text>
                    <text text-anchor="middle" x="0" y="20" fill="#a0aec0" font-size="14">This can take a minute the first time - it'll load instantly after that.</text>
                `;
            } catch (e) {}
        }

        panelContent.innerHTML = `
            <p class="eyebrow">Career graph</p>
            <h2 class="display">Combining your conversations</h2>
            <p class="lede">Building your combined career map - this can take a minute the first time. Once it's ready, it'll load instantly from here on.</p>
        `;
    }

    function renderEmpty(message) {
        if (layer) {
            try { layer.innerHTML = ''; } catch (e) {}
        }

        panelContent.innerHTML = `
            <p class="eyebrow">Career graph</p>
            <h2 class="display">Your map is waiting</h2>
            <p class="lede">${esc(message)}</p>
            <div style="margin-top:20px;">
                <a href="#explore" class="btn-gold sm" style="display:inline-flex; text-decoration:none; align-items:center; gap:6px;">
                    Go to Explore Chat
                    <svg width="12" height="12"><use href="#arrow"/></svg>
                </a>
            </div>
            <p class="whisper" style="margin-top:28px;">Share even one real hobby or interest and your directions will appear.</p>
        `;
    }

    // The free-tier backend spins down when idle and can take up to
    // ~30-50s to wake back up on the next request, which used to look
    // like a flat "we couldn't reach the server" failure with an
    // empty graph. Shown while a fetch is in flight or being retried,
    // never a permanent state.
    function renderMapping() {
        if (layer) {
            try {
                layer.innerHTML = `
                    <text text-anchor="middle" x="0" y="0" fill="#a0aec0" font-size="15">Mapping your directions...</text>
                `;
            } catch (e) {}
        }

        panelContent.innerHTML = `
            <p class="eyebrow">Career graph</p>
            <h2 class="display">Mapping your directions</h2>
            <p class="lede">This can take a little longer if the server just woke up.</p>
        `;
    }

    // The genuine "we tried and it's still not reachable" state, after
    // the retry schedule is exhausted. Unlike renderEmpty (which
    // correctly points a student with no real data yet to Explore),
    // this is a reachability failure - the fix is to retry the same
    // request, never to navigate away to chat.
    function renderServerError() {
        if (layer) {
            try { layer.innerHTML = ''; } catch (e) {}
        }

        panelContent.innerHTML = `
            <p class="eyebrow">Career graph</p>
            <h2 class="display">Your map is waiting</h2>
            <p class="lede">We couldn't reach the server. Please try again.</p>
            <div style="margin-top:20px;">
                <button type="button" class="btn-gold sm" id="graphRetryBtn">Try again</button>
            </div>
        `;
        $('#graphRetryBtn')?.addEventListener('click', () => loadTree());
    }

    const RETRY_DELAYS_MS = [2000, 5000, 10000];

    function delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    async function loadTree(attempt = 0) {

        const combined = K.isConnectThreadsOn();
        const sessionId = K.getResultsSessionId();

        if (!sessionId) {
            renderEmpty("Your career map is waiting! Head over to Explore and start a conversation first.");
            return;
        }

        if (attempt === 0) {
            if (combined) renderLoadingCombined();
            else renderMapping();
        }

        try {

            const scopeParam = combined ? '&scope=all' : '';
            const response = await fetch(`${K.API_BASE_URL}/api/career-tree/${sessionId}?token=${encodeURIComponent(K.getAuthToken())}${scopeParam}`);

            if (response.status === 404) {
                const body = await response.json().catch(() => null);
                renderEmpty(body?.detail || "Your career map needs a bit more chat detail! Tell Kindling about what you enjoy doing in Explore to see connected careers.");
                return;
            }

            // A 5xx here is usually the proxy answering while the free-tier
            // instance is still booting, not a real application error -
            // treat it the same as a network failure and retry.
            if (!response.ok) throw new Error(`Server returned ${response.status}`);

            const data = await response.json();
            treeNodes = data.nodes || [];
            treeEdges = data.edges || [];

            if (treeNodes.length <= 1) {
                renderEmpty("No directions found yet. Share more about your interests in Explore.");
                return;
            }

            buildGraph();

            // FIX 2: Restore last selected node if user came back from chat
            let restoreId = null;
            try {
                restoreId = sessionStorage.getItem('kindling_graph_selected');
            } catch (e) {}

            if (restoreId && byId[restoreId]) {
                selectNode(restoreId);
            } else {
                renderOverview();
            }

        }

        catch (error) {
            console.error(`Failed to load career tree (attempt ${attempt + 1}):`, error);

            if (attempt < RETRY_DELAYS_MS.length) {
                if (!combined) renderMapping();
                await delay(RETRY_DELAYS_MS[attempt]);
                await loadTree(attempt + 1);
                return;
            }

            renderServerError();
        }

    }

    function leafCount(id) {
        const kids = childrenOf[id];
        if (!kids || !kids.length) return 1;
        return kids.reduce((sum, k) => sum + leafCount(k), 0);
    }

    function layoutTree() {

        const hub = byId.you;
        hub.x = 0; hub.y = 0;

        const areaIds = childrenOf.you || [];
        const FULL = Math.PI * 2;
        const areaWeights = areaIds.map(leafCount);
        const totalWeight = areaWeights.reduce((a, b) => a + b, 0) || 1;

        let cursor = -Math.PI / 2;

        areaIds.forEach((areaId, i) => {

            const width = FULL * areaWeights[i] / totalWeight;
            const centerAng = cursor + width / 2;
            cursor += width;

            const areaNode = byId[areaId];
            areaNode.ang = centerAng;
            areaNode.x = Math.cos(centerAng) * AREA_R;
            areaNode.y = Math.sin(centerAng) * AREA_R;

            const fieldIds = childrenOf[areaId] || [];
            const fieldWeights = fieldIds.map(leafCount);
            const fieldTotalWeight = fieldWeights.reduce((a, b) => a + b, 0) || 1;
            const areaSpread = width * 0.88;
            let fieldCursor = centerAng - areaSpread / 2;

            fieldIds.forEach((fieldId, j) => {

                const fWidth = areaSpread * fieldWeights[j] / fieldTotalWeight;
                const fCenterAng = fieldCursor + fWidth / 2;
                fieldCursor += fWidth;

                const fieldNode = byId[fieldId];
                fieldNode.ang = fCenterAng;
                const fr = FIELD_R + (j % 3) * 34;
                fieldNode.x = Math.cos(fCenterAng) * fr;
                fieldNode.y = Math.sin(fCenterAng) * fr;

                const careerIds = childrenOf[fieldId] || [];
                const fieldSpread = fWidth * 0.92;
                const m = careerIds.length;

                careerIds.forEach((careerId, k) => {
                    const t = m === 1 ? 0 : (k / (m - 1)) - 0.5;
                    const cAng = fCenterAng + t * fieldSpread;
                    const careerNode = byId[careerId];
                    careerNode.ang = cAng;
                    const r = CAREER_R + (k % 3) * 40;
                    careerNode.x = Math.cos(cAng) * r;
                    careerNode.y = Math.sin(cAng) * r;
                });

            });

        });

    }

    function buildGraph() {

        layer.remove();
        layer = el('g', { id: 'graphLayer' }, gsvg);

        byId = {}; childrenOf = {}; neighbors = {}; nodeEls = {}; edgeEls = [];

        treeNodes.forEach(n => { byId[n.id] = { ...n }; });
        treeEdges.filter(e => e.kind === 'branch').forEach(e => {
            (childrenOf[e.source] = childrenOf[e.source] || []).push(e.target);
        });
        treeNodes.forEach(n => { neighbors[n.id] = new Set([n.id]); });
        treeEdges.forEach(e => {
            neighbors[e.source]?.add(e.target);
            neighbors[e.target]?.add(e.source);
        });

        layoutTree();

        const edgeLayer = el('g', {}, layer);
        treeEdges.forEach(e => {
            const P = byId[e.source], Q = byId[e.target];
            if (!P || !Q) return;
            const mx = (P.x + Q.x) / 2 + (Q.y - P.y) * 0.1;
            const my = (P.y + Q.y) / 2 - (Q.x - P.x) * 0.1;
            const isCross = e.kind === 'cross';
            const stroke = isCross ? 'var(--muted)' : colorOf[Q.type];
            const path = el('path', {
                class: 'edge ' + (isCross ? 'cross' : 'branch'),
                d: `M${P.x} ${P.y} Q${mx} ${my} ${Q.x} ${Q.y}`,
                stroke
            }, edgeLayer);
            edgeEls.push({ e, path });
        });

        const SIZES = {
            area: { core: 5, halo: 16, thresh: 0.3, lx: 14, ly: 18 },
            field: { core: 4, halo: 12, thresh: 0.28, lx: 11, ly: 15 },
            career: { core: 3, halo: 9, thresh: 0.25, lx: 9, ly: 12 }
        };

        const nodeLayer = el('g', {}, layer);
        treeNodes.forEach(n => {
            const node = byId[n.id];
            let opts;

            if (node.type === 'hub') {
                opts = { core: 7, halo: 30, lx: 0, ly: 34, anchor: 'middle', cls: 'hub' };
            }
            else {
                const s = SIZES[node.type] || SIZES.career;
                const c = Math.cos(node.ang || 0), sn = Math.sin(node.ang || 0);
                opts = {
                    core: s.core, halo: s.halo, cls: node.type,
                    anchor: c > s.thresh ? 'start' : c < -s.thresh ? 'end' : 'middle',
                    lx: c > s.thresh ? s.lx : c < -s.thresh ? -s.lx : 0,
                    ly: Math.abs(c) <= s.thresh ? (sn < 0 ? -s.ly : s.ly + 6) : 4
                };
            }

            const g = drawNode(nodeLayer, node, gGlow, opts);
            nodeEls[n.id] = g;
            if (opened.has(n.id)) g.classList.add('visited');

            if (node.type !== 'hub') {
                const truncated = mapLabel(node.label);
                if (truncated !== node.label) {
                    const textEl = g.querySelector('text');
                    if (textEl) textEl.textContent = truncated;
                }
                el('title', {}, g).textContent = node.label;
            }

            g.addEventListener('mouseenter', () => light(n.id));
            g.addEventListener('mouseleave', () => light(selected));
            g.addEventListener('focus', () => light(n.id));
            g.addEventListener('blur', () => light(selected));
            onActivate(g, () => { if (!dragMoved) selectNode(n.id); });
        });

        resolveLabelCollisions();
        applyFilter();

    }

    const LABEL_MARGIN = 7;

    function labelWorldBox(node, g) {
        const textEl = g.querySelector('text');
        if (!textEl) return null;
        const box = textEl.getBBox();
        return {
            left: box.x + node.x - LABEL_MARGIN, right: box.x + box.width + node.x + LABEL_MARGIN,
            top: box.y + node.y - LABEL_MARGIN, bottom: box.y + box.height + node.y + LABEL_MARGIN
        };
    }

    function boxesOverlap(a, b) {
        return !(a.right < b.left || b.right < a.left || a.bottom < b.top || b.bottom < a.top);
    }

    function resolveLabelCollisions() {
        {
            // Includes 'area' too - a lone field sits at the exact same
            // angle as its one parent area (layoutTree centers a
            // single child directly on the parent's own ray), so their
            // labels can collide along that ray. Excluding area nodes
            // here meant that specific collision could never resolve.
            const items = treeNodes
                .filter(n => n.type === 'area' || n.type === 'field' || n.type === 'career')
                .map(n => ({ node: byId[n.id], g: nodeEls[n.id] }))
                .filter(it => it.g);

            for (let pass = 0; pass < 14; pass++) {
                let changed = false;

                for (let i = 0; i < items.length; i++) {
                    for (let j = i + 1; j < items.length; j++) {
                        const a = items[i], b = items[j];
                        const boxA = labelWorldBox(a.node, a.g), boxB = labelWorldBox(b.node, b.g);
                        if (!boxA || !boxB || !boxesOverlap(boxA, boxB)) continue;

                        const target = Math.hypot(a.node.x, a.node.y) >= Math.hypot(b.node.x, b.node.y) ? a : b;
                        const other = target === a ? b : a;

                        const angDiff = (target.node.ang ?? 0) - (other.node.ang ?? 0);
                        const angPush = angDiff === 0 ? 0.03 : Math.sign(angDiff) * 0.03;
                        const newAng = (target.node.ang ?? 0) + angPush;
                        const newR = Math.hypot(target.node.x, target.node.y) + 16;

                        target.node.ang = newAng;
                        target.node.x = Math.cos(newAng) * newR;
                        target.node.y = Math.sin(newAng) * newR;
                        target.g.setAttribute('transform', `translate(${target.node.x} ${target.node.y})`);
                        changed = true;
                    }
                }

                if (!changed) break;
            }
        }

        edgeEls.forEach(({ e, path }) => {
            const P = byId[e.source], Q = byId[e.target];
            if (!P || !Q) return;
            const mx = (P.x + Q.x) / 2 + (Q.y - P.y) * 0.1;
            const my = (P.y + Q.y) / 2 - (Q.x - P.x) * 0.1;
            path.setAttribute('d', `M${P.x} ${P.y} Q${mx} ${my} ${Q.x} ${Q.y}`);
        });
    }

    function light(id) {
        gsvg.classList.toggle('is-focused', !!id);
        const set = id ? (neighbors[id] || new Set()) : new Set();
        Object.entries(nodeEls).forEach(([k, g]) => g.classList.toggle('is-lit', set.has(k)));
        edgeEls.forEach(({ e, path }) => path.classList.toggle('is-lit', !!id && (e.source === id || e.target === id)));
    }

    const chip = id => {
        const n = byId[id];
        if (!n) return '';
        return `<li><button data-go="${id}"><i style="background:${colorOf[n.type]}"></i>${esc(n.label)}</button></li>`;
    };

    function linkItem(fromId, toId) {
        const n = byId[toId];
        if (!n) return '';
        const edge = treeEdges.find(e => e.kind === 'cross' &&
            ((e.source === fromId && e.target === toId) || (e.source === toId && e.target === fromId)));
        const reason = edge?.reason || '';
        return `<li><button data-go="${toId}"><i style="background:${colorOf[n.type]}"></i>${esc(n.label)}</button>${reason ? `<p class="link-reason">${esc(reason)}</p>` : ''}</li>`;
    }

    function breadcrumbFor(node) {
        const chain = [];
        let p = node.parent ? byId[node.parent] : null;
        while (p && p.type !== 'hub') {
            chain.unshift(p);
            p = p.parent ? byId[p.parent] : null;
        }
        return chain;
    }

    function renderOverview() {
        const areaIds = childrenOf.you || [];
        panelContent.innerHTML = `
      <p class="eyebrow">Career graph</p>
      <h2 class="display">A universe<br>of possibilities</h2>
      <p class="lede">Fields and careers connected to what you've been curious about. Select any star to explore it here.</p>
      <div class="panel-block">
        <p class="section-label">How to read the map</p>
        <ul class="legend">
          <li><i class="dot-hub"></i>The center of your exploration</li>
          <li><i class="dot-area"></i>Areas of interest</li>
          <li><i class="dot-related"></i>Related fields</li>
          <li><i class="dot-direction"></i>Possible directions</li>
        </ul>
      </div>
      ${areaIds.length ? `<div class="panel-block"><p class="section-label">Start with an area</p><ul class="jump-list">${areaIds.map(chip).join('')}</ul></div>` : ''}
      <p class="whisper" style="margin-top:30px">Many paths. One curious you.</p>`;
    }

    function renderNode(id) {

        const node = byId[id];
        const color = colorOf[node.type];
        const crumbs = breadcrumbFor(node);
        const kids = childrenOf[id] || [];
        const related = [...(neighbors[id] || [])].filter(nid => nid !== id && nid !== node.parent && !kids.includes(nid));

        const wasOpenedBefore = opened.has(id) && selected !== id;

        const qs = node.type === 'career'
            ? [`What does a day as a ${lc(node.label)} look like?`, `How do people get into ${lc(node.label)} work?`]
            : [`What questions does ${lc(node.label)} try to answer?`, `How is ${lc(node.label)} connected to what I've explored?`];

        const parentNode = node.parent ? byId[node.parent] : null;
        const why = node.why || (parentNode ? `Branches from ${parentNode.label}.${parentNode.why ? ' ' + parentNode.why : ''}` : '');

        const branchLabel = branchSectionLabel[node.type];

        panelContent.innerHTML = `
      <button class="link-btn" data-overview>
        <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M11 6H2M5.5 2.5 2 6l3.5 3.5" stroke="currentColor" stroke-width="1.3" fill="none"/></svg>Back to the whole map</button>
      <p class="node-kind"><i style="background:${color};box-shadow:0 0 8px ${color}"></i>${kindName[node.type] || ''}</p>
      <h2 class="node-title">${esc(node.label)}</h2>
      ${crumbs.length ? `<p class="node-path">${crumbs.map(c => `<button data-go="${c.id}">${esc(c.label)}</button>`).join(' &rarr; ')} &rarr; ${esc(node.label)}</p>` : ''}
      ${node.description ? `<div class="panel-block"><p>${esc(node.description)}</p></div>` : ''}
      ${wasOpenedBefore ? `<p class="seen-note"><svg width="10" height="10" aria-hidden="true"><use href="#spark"/></svg>You've opened this before</p>` : ''}
      ${node.tasks?.length ? `<div class="panel-block"><p class="section-label">What the work looks like</p><ul class="task-list">${node.tasks.map(t => `<li>${esc(t)}</li>`).join('')}</ul></div>` : ''}
      ${node.tryIt ? `<div class="panel-block"><p class="section-label">Try it out</p><div class="try-card"><p>${esc(node.tryIt.text)}</p>
        <button class="btn-line" data-ask="I want to try this small task: ${esc(node.tryIt.text)} Can you walk me through it?">Try it with Kindling</button></div></div>` : ''}
      ${why ? `<div class="panel-block"><p class="section-label">Connected to your exploration</p><p>${esc(why)}</p></div>` : ''}
      ${kids.length ? `<div class="panel-block"><p class="section-label">${branchLabel}</p><ul class="jump-list">${kids.map(chip).join('')}</ul></div>` : ''}
      ${related.length ? `<div class="panel-block"><p class="section-label">Also linked to</p><ul class="link-list">${related.map(rid => linkItem(id, rid)).join('')}</ul></div>` : ''}
      <div class="panel-block"><p class="section-label">Questions you could ask</p>
        <ul class="q-list">${qs.map(q => `<li><button data-ask="${esc(q)}">${esc(q)}<svg width="12" height="12"><use href="#arrow"/></svg></button></li>`).join('')}</ul></div>
      <div class="panel-cta"><button class="btn-gold sm" data-ask="Tell me more about ${esc(lc(node.label))}.">Explore this in a conversation</button></div>`;
        panel.scrollTop = 0;

    }

    let activeArea = null, activeStartedAt = null;

    function areaAxisFor(id) {
        let n = byId[id];
        while (n && n.type !== 'area') n = n.parent ? byId[n.parent] : null;
        return n ? LETTER_TO_AXIS[n.riasec] : null;
    }

    function logNodeTime(area, startedAt, endedAt) {
        const sessionId = K.getSessionId();
        if (!sessionId || !area || endedAt - startedAt < 500) return;

        fetch(`${K.API_BASE_URL}/api/events/log`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionId,
                event_type: 'node_time',
                event_data: {
                    area,
                    startedAt: new Date(startedAt).toISOString(),
                    endedAt: new Date(endedAt).toISOString()
                },
                token: K.getAuthToken()
            })
        }).catch(() => {});
    }

    function closeActiveNodeTimer() {
        if (activeArea && activeStartedAt) logNodeTime(activeArea, activeStartedAt, Date.now());
        activeArea = null;
        activeStartedAt = null;
    }

    addEventListener('hashchange', () => { if (location.hash !== '#graph') closeActiveNodeTimer(); });
    addEventListener('beforeunload', closeActiveNodeTimer);

    function selectNode(id) {
        closeActiveNodeTimer();

        selected = id;

        // FIX 2: Remember selection across page navigation
        try {
            if (id) sessionStorage.setItem('kindling_graph_selected', id);
            else sessionStorage.removeItem('kindling_graph_selected');
        } catch (e) {}

        if (id) {
            opened.add(id);
            nodeEls[id]?.classList.add('visited');
            if (graphFilter === 'opened') applyFilter();
        }

        Object.entries(nodeEls).forEach(([k, g]) => g.classList.toggle('is-selected', k === id));
        light(id);

        if (id) {
            renderNode(id);
            activeArea = areaAxisFor(id);
            activeStartedAt = Date.now();
            if (graphLayout.classList.contains('is-fullscreen')) setFsPanelOpen(true);
        }
        else {
            renderOverview();
            setFsPanelOpen(false);
        }
    }

    panel.addEventListener('click', e => {

        const goBtn = e.target.closest('[data-go]');
        if (goBtn) return selectNode(goBtn.dataset.go);

        if (e.target.closest('[data-overview]')) return selectNode(null);

        const askBtn = e.target.closest('[data-ask]');
        if (askBtn) {
            const node = selected ? byId[selected] : null;

            /*
             * Only the main CTA ("Explore this in a conversation")
             * starts the guided intro flow (plain explanation + real
             * "Try a small task" / "Ask a doubt" buttons) — "Try it
             * with Kindling" and each "Questions you could ask" item
             * already carry a specific real question, so they keep
             * auto-sending straight into open conversation.
             */
            const isIntroFlow = !!askBtn.closest('.panel-cta');

            if (node) {
                try {
                    sessionStorage.setItem('kindling_context_occupation', JSON.stringify({
                        id: node.soc || node.id,
                        title: node.fullTitle || node.label,
                        description: node.description || null,
                        tasks: node.tasks || null,
                        prefillMessage: askBtn.dataset.ask,
                        isIntroFlow
                    }));
                }
                catch (error) {}
            }

            location.hash = 'explore';
        }

    });

    document.addEventListener('keydown', e => { if (e.key === 'Escape' && document.body.dataset.page === 'graph' && selected) selectNode(null); });

    function applyFilter() {
        const keep = new Set(['you']);
        if (graphFilter === 'opened') {
            opened.forEach(id => {
                keep.add(id);
                let p = byId[id]?.parent;
                while (p) { keep.add(p); p = byId[p]?.parent; }
            });
        }
        Object.entries(nodeEls).forEach(([id, g]) => g.classList.toggle('is-hidden', graphFilter === 'opened' && !keep.has(id)));
        edgeEls.forEach(({ e, path }) => path.classList.toggle('is-hidden', graphFilter === 'opened' && !(keep.has(e.source) && keep.has(e.target))));
    }

    $$('.graph-filter [role=radio]').forEach(b => b.addEventListener('click', () => {
        graphFilter = b.dataset.filter;
        $$('.graph-filter [role=radio]').forEach(x => x.setAttribute('aria-checked', String(x === b)));
        applyFilter();
        if (graphFilter === 'opened' && !opened.size) toast("Open a star first, and it will show up here");
    }));

    let view = { x: 0, y: 0, k: 1 };
    const applyView = () => layer.setAttribute('transform', `translate(${view.x} ${view.y}) scale(${view.k})`);
    const svgPoint = (cx, cy) => {
        const r = gsvg.getBoundingClientRect(), vb = gsvg.viewBox.baseVal;
        const s = Math.max(vb.width / r.width, vb.height / r.height);
        return { x: vb.x + vb.width / 2 + (cx - r.left - r.width / 2) * s, y: vb.y + vb.height / 2 + (cy - r.top - r.height / 2) * s, s };
    };
    function zoomAt(f, px = 0, py = 0) {
        const k = Math.min(3, Math.max(0.6, view.k * f)); f = k / view.k;
        view.x = px - (px - view.x) * f; view.y = py - (py - view.y) * f; view.k = k; applyView();
    }
    frame.addEventListener('wheel', e => { e.preventDefault(); const p = svgPoint(e.clientX, e.clientY); zoomAt(e.deltaY < 0 ? 1.12 : 1 / 1.12, p.x, p.y); }, { passive: false });
    $('#zoomIn').addEventListener('click', () => zoomAt(1.25));
    $('#zoomOut').addEventListener('click', () => zoomAt(0.8));
    const fitK = () => (frame.clientWidth && frame.clientWidth < 600 ? 1.3 : 1);
    $('#zoomFit').addEventListener('click', () => { view = { x: 0, y: 0, k: fitK() }; applyView(); });

    // ── Fullscreen ───────────────────────────────────────────
    // Fullscreens #graphLayout (not just the tree) so the starfield
    // canvas, reparented into it for the duration by the shared
    // K.setupFullscreen helper, keeps drifting behind the tree instead
    // of vanishing outside the fullscreened subtree.
    const fsBtn = $('#graphFullscreen'), graphLayout = $('#graphLayout');

    K.setupFullscreen({
        container: graphLayout,
        button: fsBtn,
        // Hidden by default on entering fullscreen (even if a node was
        // already selected before), and cleaned up when leaving - Esc
        // closes fullscreen itself but was never meant to be relied on
        // to close the panel too.
        onChange: () => setFsPanelOpen(false)
    });

    $('#graphPanelClose')?.addEventListener('click', () => setFsPanelOpen(false));

    // The panel now pushes the graph area rather than overlaying it
    // (see .map-layout.is-fullscreen .info-pane in screens.css) - once
    // that width transition actually finishes, refit the graph to
    // whatever space is left, same #zoomFit logic the toolbar button
    // already uses. Filtered to the 'width' property specifically
    // since 'padding' transitions on the same element and ends at
    // roughly the same time, which would otherwise fire this twice.
    panel.addEventListener('transitionend', e => {
        if (e.propertyName !== 'width' || !graphLayout.classList.contains('is-fullscreen')) return;
        view = { x: 0, y: 0, k: fitK() };
        applyView();
    });

    // Fullscreen only: clicking empty graph space (not a node or the
    // toolbar/filter) dismisses the slide-over panel without touching
    // the underlying selection.
    frame.addEventListener('click', e => {
        if (!fsPanelOpen || !graphLayout.classList.contains('is-fullscreen')) return;
        if (e.target.closest('.graph-tools, .graph-filter, .node')) return;
        setFsPanelOpen(false);
    });

    let drag = null, dragMoved = false;
    frame.addEventListener('pointerdown', e => { if (e.target.closest('.graph-tools, .graph-filter')) return; drag = { sx: e.clientX, sy: e.clientY, ox: view.x, oy: view.y }; dragMoved = false; });
    addEventListener('pointermove', e => {
        if (!drag) return;
        const s = svgPoint(0, 0).s, dx = (e.clientX - drag.sx) * s, dy = (e.clientY - drag.sy) * s;
        if (!dragMoved && Math.hypot(dx, dy) < 5) return;
        if (!dragMoved) { dragMoved = true; frame.classList.add('is-panning'); }
        view.x = drag.ox + dx; view.y = drag.oy + dy; applyView();
    });
    addEventListener('pointerup', () => { if (!drag) return; drag = null; frame.classList.remove('is-panning'); setTimeout(() => { dragMoved = false; }, 0); });

    function refreshScopeBar() {
        K.renderScopeBar($('#graphScopeBar'), loadTree);
    }

    K.onRoute.graph = () => {
        refreshScopeBar();
        loadTree();
        requestAnimationFrame(() => { view.k = fitK(); applyView(); });
    };

    window.addEventListener('kindling:scope-change', () => {
        if (document.body.dataset.page !== 'graph') return;
        refreshScopeBar();
        loadTree();
    });

})();