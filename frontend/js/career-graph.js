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
    K.interceptFullscreenNavLinks(panel);

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

    // What the student has added on top of the server's first view:
    // "Show more" layers (real occupations, from POST /api/career-tree/
    // more) and example specialisations under a career. Kept per
    // thread + scope so it survives leaving the page and coming back,
    // and re-merged onto each fresh tree (see loadTree). `remaining`
    // is what the last "Show more" on a node said was still left.
    const extras = {};
    let treeKey = '';
    const extrasFor = () => extras[treeKey] || (extras[treeKey] = { nodes: [], edges: [], remaining: {}, noSpecs: {} });

    // A hide/focus preference changes which occupations are allowed
    // on the map at all - anything added earlier may no longer be.
    window.addEventListener('kindling:preferences-change', () => {
        Object.keys(extras).forEach(k => delete extras[k]);
    });

    const AREA_R = 175, FIELD_R = 265, CAREER_R = 350;

    function mapLabel(label) {
        return label && label.length > 22 ? label.slice(0, 21).trimEnd() + '…' : label;
    }

    const kindName = {
        hub: 'Center of your exploration', area: 'Area of interest',
        field: 'Related field', career: 'Possible direction',
        spec: 'Example specialisation'
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

            treeKey = `${sessionId}|${combined ? 'all' : 'single'}`;
            const remembered = extrasFor();
            mergeIntoTree(remembered.nodes, remembered.edges, false);

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

                    const specIds = childrenOf[careerId] || [];
                    const specSpread = Math.min(0.5, 0.1 * specIds.length);
                    specIds.forEach((specId, s) => {
                        const st = specIds.length === 1 ? 0 : (s / (specIds.length - 1)) - 0.5;
                        const sAng = cAng + st * specSpread;
                        const sr = r + 78 + (s % 2) * 30;
                        const specNode = byId[specId];
                        specNode.ang = sAng;
                        specNode.x = Math.cos(sAng) * sr;
                        specNode.y = Math.sin(sAng) * sr;
                    });
                });

            });

        });

    }

    function buildGraph() {

        layer.remove();
        layer = el('g', { id: 'graphLayer' }, gsvg);

        byId = {}; childrenOf = {}; neighbors = {}; nodeEls = {}; edgeEls = [];

        treeNodes.forEach(n => { byId[n.id] = { ...n }; });
        // 'example' edges (a career's example specialisations) are
        // parent->child links too, just drawn dashed.
        treeEdges.filter(e => e.kind === 'branch' || e.kind === 'example').forEach(e => {
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
                class: 'edge ' + (isCross ? 'cross' : e.kind === 'example' ? 'example' : 'branch'),
                d: `M${P.x} ${P.y} Q${mx} ${my} ${Q.x} ${Q.y}`,
                stroke
            }, edgeLayer);
            edgeEls.push({ e, path });
        });

        const SIZES = {
            area: { core: 5, halo: 16, thresh: 0.3, lx: 14, ly: 18 },
            field: { core: 4, halo: 12, thresh: 0.28, lx: 11, ly: 15 },
            career: { core: 3, halo: 9, thresh: 0.25, lx: 9, ly: 12 },
            spec: { core: 2.6, halo: 7, thresh: 0.25, lx: 8, ly: 11 }
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

            // Hollow: an example of how people specialise, not a real
            // occupation from the dataset like every filled star is.
            if (node.type === 'spec') {
                const circles = g.querySelectorAll('circle');
                circles[3].setAttribute('fill', 'none');
                circles[3].setAttribute('stroke', colorOf.spec);
                circles[3].setAttribute('stroke-width', '1.2');
                circles[4].remove();
            }

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
                .filter(n => n.type === 'area' || n.type === 'field' || n.type === 'career' || n.type === 'spec')
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
          <li><i class="dot-example"></i>Example specialisations, once you ask for them</li>
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

        // Most career/field labels are real plural O*NET-style titles
        // ("Fine Artists", "Designers") - plugging those into a
        // singular-only template read as "a day as a fine artists" and
        // "does Designers try to answer". Heuristic only (last word
        // ending in 's'), not true grammatical number, but it's right
        // for the occupation-title style labels these actually are.
        const plural = /[a-z]s$/i.test(node.label.trim().split(/\s+/).pop());
        const article = plural ? '' : 'a ';

        const parentNode = node.parent ? byId[node.parent] : null;

        const qs = node.type === 'hub'
            ? ["What patterns have you noticed in what I've shared?", "Which direction should I explore first?"]
            : node.type === 'spec'
            ? [`What does specialising in ${lc(node.label)} involve?`, `How do people get started in ${lc(node.label)}?`]
            : node.type === 'career'
            ? [`What does a day as ${article}${lc(node.label)} look like?`, `How do people get into work as ${article}${lc(node.label)}?`]
            : [`What questions ${plural ? 'do' : 'does'} ${lc(node.label)} try to answer?`, `How ${plural ? 'are' : 'is'} ${lc(node.label)} connected to what I've explored?`];

        const why = node.type === 'spec'
            ? `One of the ways people specialise as ${lc(parentNode.fullTitle || parentNode.label)}. It's an example to give you a picture, not a separate official occupation.`
            : node.why || (parentNode ? `Branches from ${parentNode.label}.${parentNode.why ? ' ' + parentNode.why : ''}` : '');

        const branchLabel = branchSectionLabel[node.type];
        const state = extrasFor();

        // Area and field nodes: one more layer of real occupations per
        // click, until the backend says nothing is left.
        const canShowMore = node.type === 'area' || node.type === 'field';
        const moreBlock = !canShowMore ? '' : state.remaining[id] === 0
            ? `<div class="panel-block"><p class="depth-note">That's everything that fits here for now.</p></div>`
            : `<div class="panel-block"><button class="btn-line" data-more>Show more in ${esc(node.label)}</button></div>`;

        // Career nodes: where the work happens (filled in by
        // loadWhere once the student has stayed on this node a
        // moment) and, only when asked for, example specialisations.
        const whereBlock = node.type !== 'career' ? '' :
            `<div class="panel-block"><p class="section-label">Where this work happens</p><div data-where><p class="depth-note">Looking this up…</p></div></div>`;
        const specBlock = node.type !== 'career' ? '' : `<div class="panel-block"><p class="section-label">Ways people specialise</p>${
            kids.length
                ? `<ul class="jump-list">${kids.map(chip).join('')}</ul><p class="depth-note">Examples, shown as hollow stars on the map. Not separate official occupations.</p>`
                : state.noSpecs[id]
                ? `<p class="depth-note">No well-established specialisations to show for this one.</p>`
                : `<button class="btn-line" data-specialise>Show examples on the map</button>`
        }</div>`;

        const askTopic = node.type === 'spec'
            ? `${lc(node.label)} as a specialisation within ${lc(parentNode.fullTitle || parentNode.label)}`
            : lc(node.label);

        panelContent.innerHTML = `
      <button class="link-btn" data-overview>
        <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M11 6H2M5.5 2.5 2 6l3.5 3.5" stroke="currentColor" stroke-width="1.3" fill="none"/></svg>Back to the whole map</button>
      <p class="node-kind"><i style="background:${color};box-shadow:0 0 8px ${color}"></i>${kindName[node.type] || ''}</p>
      <h2 class="node-title">${esc(node.label)}</h2>
      ${node.type === 'field' && node.officialTitle && node.officialTitle !== node.label ? `<p class="node-official-title">Official category: ${esc(node.officialTitle)}</p>` : ''}
      ${crumbs.length ? `<p class="node-path">${crumbs.map(c => `<button data-go="${c.id}">${esc(c.label)}</button>`).join(' &rarr; ')} &rarr; ${esc(node.label)}</p>` : ''}
      ${node.description ? `<div class="panel-block"><p>${esc(node.description)}</p></div>` : ''}
      ${wasOpenedBefore ? `<p class="seen-note"><svg width="10" height="10" aria-hidden="true"><use href="#spark"/></svg>You've opened this before</p>` : ''}
      ${node.tasks?.length ? `<div class="panel-block"><p class="section-label">What the work looks like</p><ul class="task-list">${node.tasks.map(t => `<li>${esc(t)}</li>`).join('')}</ul></div>` : ''}
      ${node.tryIt ? `<div class="panel-block"><p class="section-label">Try it out</p><div class="try-card"><p>${esc(node.tryIt.text)}</p>
        <button class="btn-line" data-ask="I want to try this small task: ${esc(node.tryIt.text)} Can you walk me through it?">Try it with Kindling</button></div></div>` : ''}
      ${why ? `<div class="panel-block"><p class="section-label">${node.type === 'spec' ? 'About this example' : 'Connected to your exploration'}</p><p>${esc(why)}</p></div>` : ''}
      ${whereBlock}
      ${specBlock}
      ${kids.length && node.type !== 'career' ? `<div class="panel-block"><p class="section-label">${branchLabel}</p><ul class="jump-list">${kids.map(chip).join('')}</ul></div>` : ''}
      ${moreBlock}
      ${related.length ? `<div class="panel-block"><p class="section-label">Also linked to</p><ul class="link-list">${related.map(rid => linkItem(id, rid)).join('')}</ul></div>` : ''}
      <div class="panel-block"><p class="section-label">Questions you could ask</p>
        <ul class="q-list">${qs.map(q => `<li><button data-ask="${esc(q)}">${esc(q)}<svg width="12" height="12"><use href="#arrow"/></svg></button></li>`).join('')}</ul></div>
      <div class="panel-cta"><button class="btn-gold sm" data-ask="Tell me more about ${esc(askTopic)}.">Explore this in a conversation</button></div>`;
        panel.scrollTop = 0;

        if (node.type === 'career') loadWhere(node);

    }

    /* =====================================================
       DEPTH - "Show more", "Where this work happens" and
       "Ways people specialise"
       ===================================================== */

    // Adds nodes/edges to the tree already on screen, skipping any
    // that are already there or whose parent isn't (a remembered
    // layer can outlive the node it hung from). Returns what was
    // actually added.
    function mergeIntoTree(newNodes, newEdges, remember = true) {
        const have = new Set(treeNodes.map(n => n.id));
        const added = [];
        newNodes.forEach(n => {
            if (have.has(n.id) || !have.has(n.parent)) return;
            treeNodes.push(n);
            have.add(n.id);
            added.push(n);
        });
        const addedIds = new Set(added.map(n => n.id));
        const addedEdges = newEdges.filter(e => addedIds.has(e.target) && have.has(e.source));
        treeEdges.push(...addedEdges);

        if (remember) {
            const state = extrasFor();
            state.nodes.push(...added);
            state.edges.push(...addedEdges);
        }
        return added;
    }

    // Redraws the map with whatever was just merged in, keeping the
    // current selection and its panel.
    function redrawKeepingSelection() {
        buildGraph();
        Object.entries(nodeEls).forEach(([k, g]) => g.classList.toggle('is-selected', k === selected));
        light(selected);
        if (selected && byId[selected]) renderNode(selected);
    }

    async function showMore(id, btn) {
        const node = byId[id];
        const areaId = node.type === 'area' ? id : node.parent;
        const label = btn.textContent;
        btn.disabled = true;
        btn.textContent = 'Finding more…';

        try {
            const response = await fetch(`${K.API_BASE_URL}/api/career-tree/more`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: K.getResultsSessionId(),
                    token: K.getAuthToken(),
                    scope: K.isConnectThreadsOn() ? 'all' : 'single',
                    node_id: id,
                    shown: treeNodes.filter(n => n.type === 'career').map(n => n.soc),
                    fields: childrenOf[areaId] || []
                })
            });
            if (!response.ok) throw new Error(`Server returned ${response.status}`);

            const data = await response.json();
            const added = mergeIntoTree(data.nodes || [], data.edges || []);
            const addedCareers = added.filter(n => n.type === 'career').length;
            extrasFor().remaining[id] = addedCareers ? data.remaining : 0;
            redrawKeepingSelection();
        }
        catch (error) {
            console.error('Failed to load more careers:', error);
            toast("We couldn't load more right now. Please try again.");
            btn.disabled = false;
            btn.textContent = label;
        }
    }

    // One request per occupation per visit; the backend caches the
    // generated answer for everyone after the first time. A failure
    // isn't remembered, so the next try asks again.
    const depthRequests = new Map();
    function fetchDepth(soc) {
        if (!depthRequests.has(soc)) {
            const url = `${K.API_BASE_URL}/api/career-depth/${K.getResultsSessionId()}/${encodeURIComponent(soc)}?token=${encodeURIComponent(K.getAuthToken())}`;
            depthRequests.set(soc, fetch(url)
                .then(r => { if (!r.ok) throw new Error(`Server returned ${r.status}`); return r.json(); })
                .catch(error => {
                    console.error('Failed to load career depth:', error);
                    depthRequests.delete(soc);
                    return null;
                }));
        }
        return depthRequests.get(soc);
    }

    // Waits a moment before asking, so clicking quickly through
    // several careers doesn't spend an AI call on each one.
    const WHERE_DWELL_MS = 900;
    let whereTimer = null;
    function loadWhere(node) {
        clearTimeout(whereTimer);
        const fill = async () => {
            const depth = await fetchDepth(node.soc);
            const box = selected === node.id ? $('[data-where]', panelContent) : null;
            if (!box) return;
            const places = depth?.workplaces || [];
            if (!places.length) {
                box.innerHTML = `<p class="depth-note">We couldn't load this right now.</p>`;
                return;
            }
            box.innerHTML = `<ul class="where-list">${places.map(w =>
                `<li>${esc(w.setting)}${w.examples?.length ? `<span class="where-eg">e.g. ${w.examples.map(esc).join(', ')}</span>` : ''}</li>`
            ).join('')}</ul><p class="depth-note">Examples to give you a picture, not a complete list.</p>`;
        };
        if (depthRequests.has(node.soc)) fill();
        else whereTimer = setTimeout(fill, WHERE_DWELL_MS);
    }

    async function showSpecialisations(id, btn) {
        const node = byId[id];
        const label = btn.textContent;
        btn.disabled = true;
        btn.textContent = 'Finding examples…';

        const depth = await fetchDepth(node.soc);
        if (!depth) {
            toast("We couldn't load examples right now. Please try again.");
            btn.disabled = false;
            btn.textContent = label;
            return;
        }

        const specs = depth.specialisations || [];
        if (!specs.length) extrasFor().noSpecs[id] = true;

        // Never real occupations: type 'spec', no SOC code, and only
        // ever attached under the real career they're examples of.
        const nodes = specs.map((s, i) => ({
            id: `s:${node.soc}:${i}`, type: 'spec', label: s.name, description: s.about, parent: id
        }));
        const edges = nodes.map(n => ({ source: id, target: n.id, kind: 'example' }));
        mergeIntoTree(nodes, edges);
        redrawKeepingSelection();
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
        $('#showAllBtn').hidden = !id;

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

        const moreBtn = e.target.closest('[data-more]');
        if (moreBtn && selected) return showMore(selected, moreBtn);

        const specBtn = e.target.closest('[data-specialise]');
        if (specBtn && selected) return showSpecialisations(selected, specBtn);

        const askBtn = e.target.closest('[data-ask]');
        if (askBtn) {
            // An example specialisation isn't an occupation of its own:
            // the conversation is grounded in the real career it sits
            // under, and the question itself names the specialisation.
            const picked = selected ? byId[selected] : null;
            const node = picked?.type === 'spec' ? byId[picked.parent] : picked;

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

            K.exitFullscreenThenNavigate('explore');
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
    $('#showAllBtn').addEventListener('click', () => selectNode(null));

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

    // Fully deselects (clears the dim/focus state on the graph, not
    // just the panel) - closing the panel used to leave whatever node
    // was selected still dimming everything else, with no way back to
    // full brightness short of Esc or the "Back to the whole map" link.
    $('#graphPanelClose')?.addEventListener('click', () => selectNode(null));

    // Defensive only: panel and #graphFrame are siblings, not nested,
    // so the graph's own wheel-zoom listener below can never actually
    // fire from a wheel event over the panel - the real reason the
    // panel couldn't scroll was its fullscreen CSS using a flat
    // `overflow: hidden` (needed to clip it during the width-open
    // transition) instead of allowing vertical scroll once open. Fixed
    // in screens.css; this stays as a guard against that assumption
    // ever becoming false if the layout changes later.
    panel.addEventListener('wheel', e => e.stopPropagation());

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

    // Clicking empty graph space (not a node or the toolbar/filter)
    // fully deselects - in fullscreen this also closes the slide-over
    // panel as a side effect of selectNode(null), same as the panel's
    // own close button and "Back to the whole map" link. Works outside
    // fullscreen too, where there was previously no way to click back
    // to full brightness at all short of Esc.
    frame.addEventListener('click', e => {
        if (!selected) return;
        if (e.target.closest('.graph-tools, .graph-filter, .node')) return;
        selectNode(null);
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