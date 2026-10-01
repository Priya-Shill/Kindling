/* =========================================================
   EXPLORE — real chat
   Real endpoints only: POST /api/chat/start, POST
   /api/chat/message, GET /api/chat/session/{id}. Kindling's
   real flow is Kindling-initiated (it asks the first
   question), unlike the mockup's user-initiated empty state,
   so the opening question is rendered as the first message
   instead of a blank composer waiting for input.
   ========================================================= */

(() => {

    const K = window.Kindling;
    const { $, $$, esc, lc } = K;

    const feed = $('#feed'), form = $('#composer'), input = $('#ask'), sendBtn = $('.send', form);
    const threadProgress = $('#threadProgress'), threadProgressFill = $('#threadProgressFill'), threadProgressLabel = $('#threadProgressLabel');

    const threadsSidebar = $('#threadsSidebar'), threadsList = $('#threadsList');
    const threadsCollapseBtn = $('#threadsCollapse'), threadsExpandBtn = $('#threadsExpand');
    const threadsMobileToggle = $('#threadsMobileToggle'), threadsBackdrop = $('#threadsBackdrop');
    const SIDEBAR_COLLAPSE_KEY = 'kindling_threads_collapsed';

    const deleteThreadDialog = $('#deleteThreadDialog'), deleteThreadConfirmBtn = $('#deleteThreadConfirm');
    const undoToast = $('#undoToast'), undoToastText = $('#undoToastText'), undoToastBtn = $('#undoToastBtn');
    const MAX_PINS = 5;

    const contextBar = $('#contextBar'), contextBarTitle = $('#contextBarTitle');
    const contextBarTask = $('#contextBarTask'), contextBarDoubt = $('#contextBarDoubt'), contextBarClose = $('#contextBarClose');
    const doubtChips = $('#doubtChips');

    const starters = [
        'Why do people make certain choices?',
        'How do technologies change our lives?',
        'What makes a good leader?',
        'Why do some ideas spread?'
    ];

    let questionIndex = 0; // real answers given so far in the 7-question intake
    let totalQuestions = 7;
    let isLoading = false;
    let started = false;

    let activeContext = null;

    const scrollFeed = () => { feed.scrollTop = feed.scrollHeight; };

    function updateProgress() {
        if (!threadProgress) return;
        const inIntake = typeof totalQuestions === 'number' && questionIndex <= totalQuestions;

        threadProgress.hidden = !inIntake;
        threadProgressLabel.hidden = inIntake;

        if (inIntake) {
            const pct = Math.max(0, Math.min(100, Math.round((questionIndex / totalQuestions) * 100)));
            threadProgressFill.style.width = `${pct}%`;
            threadProgress.setAttribute('aria-valuenow', String(questionIndex));
            threadProgress.setAttribute('aria-valuemax', String(totalQuestions));
            threadProgress.setAttribute('aria-label', `Question ${questionIndex} of ${totalQuestions} answered`);
        }
    }

    function setLoading(loading) {
        isLoading = loading;
        input.disabled = loading;
        sendBtn.disabled = loading || !input.value.trim();
    }

    function addUser(text) {
        const d = document.createElement('div');
        d.className = 'note-user';
        d.textContent = text;
        feed.appendChild(d);
        scrollFeed();
    }

    // Shown once, right when the 7-question intake finishes - a clear,
    // obvious next step alongside the composer below, which stays
    // fully usable (this never disables it or navigates on its own).
    function addCompletionCard() {
        const wrap = document.createElement('div');
        wrap.className = 'intake-complete-card';
        wrap.innerHTML = `
            <p class="intake-complete-title">I've started noticing a few patterns</p>
            <p class="intake-complete-sub">You can see some directions connected to what you've shared, or keep chatting below to explore further.</p>
            <a href="#graph" class="btn-gold intake-complete-cta">See your directions <svg width="14" height="14"><use href="#arrow"/></svg></a>
        `;
        feed.appendChild(wrap);
        scrollFeed();
    }

    /* Helper: Formats AI responses into scannable HTML with bold emphasis and clean lists */
    function formatResponseHtml(text) {
        if (!text) return '';

        // 1. Convert markdown **bold** to <strong> tags with a gold accent
        let formatted = esc(text).replace(/\*\*(.*?)\*\*/g, '<strong style="color:#f5c46a; font-weight:600;">$1</strong>');

        // 2. Split into paragraphs based on blank lines
        const blocks = formatted.split(/\n\n+/);

        return blocks.map(block => {
            const lines = block.split('\n');
            const isBulletList = lines.length > 0 && lines.every(l => {
                const trimmed = l.trim();
                return trimmed === '' || trimmed.startsWith('- ') || trimmed.startsWith('• ') || trimmed.startsWith('* ');
            });

            if (isBulletList && lines.some(l => l.trim() !== '')) {
                const listItems = lines
                    .filter(l => l.trim() !== '')
                    .map(l => `<li style="margin-bottom:6px; line-height:1.4;">${l.trim().replace(/^[-•*]\s*/, '')}</li>`)
                    .join('');
                return `<ul style="margin:8px 0; padding-left:18px; list-style-type:disc;">${listItems}</ul>`;
            }
            return `<p style="margin-bottom:8px; line-height:1.5;">${block.replace(/\n/g, '<br>')}</p>`;
        }).join('');
    }

    function renderEmptyFeedState() {
        feed.innerHTML = `<div class="feed-empty">
      <span class="k-mark" aria-hidden="true"><svg><use href="#spark"/></svg></span>
      <h2>What's on your mind today?</h2>
      <p>Ask anything. A question, a what-if, or something you noticed and can't stop thinking about.</p>
      <div class="starters">${starters.map(s => `<button type="button" class="chip">${esc(s)}</button>`).join('')}</div>
    </div>`;
        wireChipClicks(feed);
        threadProgress && (threadProgress.textContent = 'New thread');
    }

    function wireChipClicks(container) {
        $$('.chip', container).forEach(c => c.addEventListener('click', () => {
            input.value = c.textContent;
            sendBtn.disabled = false;
            input.focus();
        }));
    }

    /*
     * `chips` can be: true (the 4 generic starters), an array of
     * specific prompt strings (e.g. one real, occupation-grounded
     * prompt), or omitted/false for none.
     */
    function addKindling(text, chips) {
        const wrap = document.createElement('div');
        wrap.className = 'note-kindling';
        wrap.innerHTML = '<span class="k-mark" aria-hidden="true"><svg><use href="#spark"/></svg></span><div class="k-body"></div>';
        const body = $('.k-body', wrap);

        if (text === null) {
            body.innerHTML = '<span class="typing" aria-label="Kindling is thinking"><i></i><i></i><i></i></span>';
        }
        else {
            body.innerHTML = K.renderMarkdown(text);

            const chipList = chips === true ? starters : Array.isArray(chips) ? chips : null;

            if (chipList && chipList.length) {
                const chipsEl = document.createElement('div');
                chipsEl.className = 'starters';
                chipsEl.innerHTML = chipList.map(s => `<button type="button" class="chip">${esc(s)}</button>`).join('');
                wireChipClicks(chipsEl);
                body.appendChild(chipsEl);
            }
        }

        feed.appendChild(wrap);
        scrollFeed();
        return body;
    }

    function takeOccupationContext() {
        try {
            const raw = sessionStorage.getItem('kindling_context_occupation');
            sessionStorage.removeItem('kindling_context_occupation');
            return raw ? JSON.parse(raw) : null;
        }
        catch (error) {
            return null;
        }
    }

    // Real plural O*NET-style titles ("Musicians and Singers") need
    // "work as X" / no article; a rarer singular label needs "a" - same
    // heuristic career-graph.js uses for its own question templates.
    function isPluralLabel(label) {
        return /[a-z]s$/i.test(String(label).trim().split(/\s+/).pop());
    }

    function buildTryPrompt(context) {
        const realTask = Array.isArray(context.tasks) && context.tasks.length ? context.tasks[0] : null;
        return realTask
            ? `Can you give me something small and doable I could try, connected to this: "${realTask}"?`
            : `Can you give me something small and doable I could try, related to ${context.title}?`;
    }

    function buildDoubtChips(context) {
        const article = isPluralLabel(context.title) ? '' : 'a ';
        return [
            `Do I need formal training to work as ${article}${lc(context.title)}?`,
            `How do people in this field actually earn a living?`,
            `Is it too late for me to start exploring this?`
        ];
    }

    // The persistent bar for a conversation that started from a real
    // Career Graph node - replaces the old one-time "Try a small task"
    // / "Ask a doubt" chips that only ever appeared once, right after
    // the intro message, with something available for the rest of the
    // conversation (a student who tries a task may still want to ask
    // a doubt afterward, and the reverse).
    function showContextBar(context) {
        if (!context?.title) return;
        contextBarTitle.textContent = context.title;
        contextBar.hidden = false;
    }

    function hideContextBar() {
        contextBar.hidden = true;
        hideDoubtChips();
    }

    function hideDoubtChips() {
        doubtChips.hidden = true;
        doubtChips.innerHTML = '';
        input.placeholder = 'Tell me what you\'ve been curious about or tinkering with lately…';
    }

    contextBarTask.addEventListener('click', () => {
        if (!activeContext) return;
        hideDoubtChips();
        sendMessage(buildTryPrompt(activeContext));
    });

    // Never auto-sends anything - focuses the composer with a real
    // placeholder and three real suggested doubts as chips, so the
    // student asks Kindling something instead of Kindling asking them
    // (clicking this used to literally send the text "Ask a doubt" as
    // a user message, which Kindling then had nothing real to answer
    // and so asked its own question back - backwards from what this
    // button is for).
    contextBarDoubt.addEventListener('click', () => {
        if (!activeContext) return;
        input.placeholder = `Ask anything about ${activeContext.title}…`;
        doubtChips.innerHTML = buildDoubtChips(activeContext)
            .map(q => `<button type="button" class="chip">${esc(q)}</button>`).join('');
        doubtChips.hidden = false;
        // These are single-use suggestions, not prefill starters -
        // clicking one sends it immediately (same real question a
        // typed doubt would) and the suggestion row goes away either
        // way, same as it does once the student types their own.
        $$('.chip', doubtChips).forEach(c => c.addEventListener('click', () => {
            hideDoubtChips();
            sendMessage(c.textContent);
        }));
        input.focus();
    });

    // Typing a real doubt instead of clicking a suggestion should
    // retire the suggestions too, the moment the student actually
    // sends it - handled where the composer's submit already runs.
    form.addEventListener('submit', () => { if (!doubtChips.hidden) hideDoubtChips(); });

    contextBarClose.addEventListener('click', () => {
        activeContext = null;
        hideContextBar();
    });

    async function showOccupationContext(context) {
        if (!context?.title) return;

        showContextBar(context);
        addKindling(`Continuing from: ${context.title}`, false);

        /*
         * The Career Graph panel's own buttons (a specific "Questions
         * you could ask" item, "Try it with Kindling", or the main
         * CTA) each carry their own real, specific text. This used to
         * only prefill the composer and leave it for the user to hit
         * send — in practice that read as "the chat box is empty,
         * I have to retype the question." Send it through the same
         * real sendMessage() the composer itself uses (same guard
         * against double-send while a request is in flight, same
         * scroll-to-message behavior), so clicking any of the three
         * buttons actually asks the question.
         */
        if (context.prefillMessage) {
            await sendMessage(context.prefillMessage, { introRequest: !!context.isIntroFlow });
        }
    }

    function renderTranscript(transcript) {
        feed.innerHTML = '';
        transcript.forEach(entry => {
            if (entry.role === 'user') addUser(entry.content);
            else addKindling(entry.content, false);
        });
        scrollFeed();
    }

    function describeSession(createdAt) {
        const created = new Date(createdAt);
        const dayStart = d => { const x = new Date(d); x.setHours(0, 0, 0, 0); return x; };
        const diffDays = Math.round((dayStart(new Date()) - dayStart(created)) / 86400000);

        const time = diffDays <= 0 ? 'Today'
            : diffDays === 1 ? 'Yesterday'
            : created.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });

        const group = diffDays <= 0 ? 'Today' : diffDays <= 7 ? 'Earlier this week' : 'Older';

        return { time, group };
    }

    const PIN_ICON = '<svg class="thread-pin-icon" viewBox="0 0 12 12" aria-hidden="true"><path d="M6 1v3.5L9 6l-1 1-2-1v3l-1 1-1-1V6L2 7 1 6l3-1.5V1z" fill="currentColor"/></svg>';

    function renderThreadRow(session) {
        const { time } = describeSession(session.created_at);
        const isCurrent = session.session_id === K.getSessionId();

        const wrap = document.createElement('div');
        wrap.className = 'thread-row-wrap' + (isCurrent ? ' is-current' : '');
        wrap.dataset.sessionId = session.session_id;

        const row = document.createElement('button');
        row.type = 'button';
        row.className = 'thread-row';
        row.title = session.label;
        if (isCurrent) row.setAttribute('aria-current', 'true');
        row.innerHTML = `
      <span class="thread-row-title">${session.pinned ? PIN_ICON : ''}<span>${esc(session.label)}</span></span>
      <div class="thread-row-time">${esc(time)}</div>`;
        row.addEventListener('click', () => openThread(session.session_id));

        const menuBtn = document.createElement('button');
        menuBtn.type = 'button';
        menuBtn.className = 'thread-row-menu-btn';
        menuBtn.setAttribute('aria-label', `Options for ${session.label}`);
        menuBtn.setAttribute('aria-haspopup', 'menu');
        menuBtn.setAttribute('aria-expanded', 'false');
        menuBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><circle cx="7" cy="2.6" r="1.3" fill="currentColor"/><circle cx="7" cy="7" r="1.3" fill="currentColor"/><circle cx="7" cy="11.4" r="1.3" fill="currentColor"/></svg>';

        const menu = document.createElement('div');
        menu.className = 'thread-row-menu';
        menu.setAttribute('role', 'menu');
        menu.hidden = true;
        menu.innerHTML = `
      <button type="button" role="menuitem" data-action="pin">${PIN_ICON}${session.pinned ? 'Unpin' : 'Pin'}</button>
      <button type="button" role="menuitem" class="danger" data-action="delete">
        <svg width="13" height="13" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 3h8M4.5 3V2a1 1 0 0 1 1-1h1a1 1 0 0 1 1 1v1M3 3l.5 7a1 1 0 0 0 1 .9h5a1 1 0 0 0 1-.9L11 3" stroke="currentColor" stroke-width="1.2" fill="none" stroke-linecap="round"/></svg>
        Delete</button>`;

        menuBtn.addEventListener('click', e => {
            e.stopPropagation();
            toggleThreadMenu(menuBtn, menu);
        });
        menu.addEventListener('click', e => {
            const btn = e.target.closest('[data-action]');
            if (!btn) return;
            e.stopPropagation();
            closeThreadMenu(menuBtn, menu);
            if (btn.dataset.action === 'pin') togglePin(session);
            else if (btn.dataset.action === 'delete') openDeleteDialog(session);
        });
        menu.addEventListener('keydown', e => onThreadMenuKeydown(e, menuBtn, menu));

        wrap.append(row, menuBtn, menu);
        return wrap;
    }

    function renderThreadsList(sessions) {
        threadsList.innerHTML = '';

        if (!sessions.length) {
            const empty = document.createElement('p');
            empty.className = 'threads-empty';
            empty.textContent = 'Your past threads will appear here.';
            threadsList.appendChild(empty);
            return;
        }

        const pinned = sessions.filter(s => s.pinned).sort((a, b) => new Date(b.pinned_at) - new Date(a.pinned_at));
        const unpinned = sessions.filter(s => !s.pinned);

        if (pinned.length) {
            const label = document.createElement('p');
            label.className = 'thread-group-label';
            label.textContent = 'Pinned';
            threadsList.appendChild(label);
            pinned.forEach(session => threadsList.appendChild(renderThreadRow(session)));
        }

        const groups = new Map();
        unpinned.forEach(session => {
            const { group } = describeSession(session.created_at);
            if (!groups.has(group)) groups.set(group, []);
            groups.get(group).push(session);
        });

        ['Today', 'Earlier this week', 'Older'].forEach(groupName => {
            const items = groups.get(groupName);
            if (!items || !items.length) return;

            const label = document.createElement('p');
            label.className = 'thread-group-label';
            label.textContent = groupName;
            threadsList.appendChild(label);

            items.forEach(session => threadsList.appendChild(renderThreadRow(session)));
        });
    }

    let openThreadMenu = null;

    function closeThreadMenu(menuBtn, menu) {
        menu.hidden = true;
        menuBtn.setAttribute('aria-expanded', 'false');
        if (openThreadMenu && openThreadMenu.menu === menu) openThreadMenu = null;
    }

    function toggleThreadMenu(menuBtn, menu) {
        if (openThreadMenu && openThreadMenu.menu !== menu) closeThreadMenu(openThreadMenu.menuBtn, openThreadMenu.menu);

        if (!menu.hidden) {
            closeThreadMenu(menuBtn, menu);
            menuBtn.focus();
            return;
        }

        menu.hidden = false;
        menuBtn.setAttribute('aria-expanded', 'true');
        openThreadMenu = { menuBtn, menu };
        menu.querySelector('button')?.focus();
    }

    function onThreadMenuKeydown(e, menuBtn, menu) {
        const items = [...menu.querySelectorAll('button')];
        const idx = items.indexOf(document.activeElement);

        if (e.key === 'ArrowDown') { e.preventDefault(); items[(idx + 1) % items.length]?.focus(); }
        else if (e.key === 'ArrowUp') { e.preventDefault(); items[(idx - 1 + items.length) % items.length]?.focus(); }
        else if (e.key === 'Escape') { e.preventDefault(); closeThreadMenu(menuBtn, menu); menuBtn.focus(); }
        else if (e.key === 'Tab') { closeThreadMenu(menuBtn, menu); }
    }

    document.addEventListener('click', e => {
        if (openThreadMenu && !e.target.closest('.thread-row-wrap')) {
            closeThreadMenu(openThreadMenu.menuBtn, openThreadMenu.menu);
        }
    });
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && openThreadMenu) {
            const { menuBtn, menu } = openThreadMenu;
            closeThreadMenu(menuBtn, menu);
            menuBtn.focus();
        }
    });

    async function togglePin(session) {
        const token = K.getAuthToken();
        if (!token) return;

        try {
            const response = await fetch(`${K.API_BASE_URL}/api/chat/session/${session.session_id}/pin`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token, pin: !session.pinned })
            });

            if (response.status === 400) {
                const body = await response.json().catch(() => null);
                K.toast(body?.detail || `You can pin up to ${MAX_PINS} threads.`);
                return;
            }

            if (!response.ok) throw new Error(`Server returned ${response.status}`);

            await loadThreads();
        }

        catch (error) {
            console.error('Failed to update pin:', error);
            K.toast("We couldn't update that. Please try again.");
        }
    }

    let pendingDeleteSession = null;
    let pendingDeleteTimer = null;
    let pendingDeleteUndone = false;

    function openDeleteDialog(session) {
        pendingDeleteSession = session;
        deleteThreadDialog.showModal();
    }

    deleteThreadConfirmBtn.addEventListener('click', () => {
        deleteThreadDialog.close();
        const session = pendingDeleteSession;
        pendingDeleteSession = null;
        if (session) beginDeleteWithUndo(session);
    });

    function onUndoDelete() {
        pendingDeleteUndone = true;
        clearTimeout(pendingDeleteTimer);
        undoToast.classList.remove('is-shown');
        undoToastBtn.removeEventListener('click', onUndoDelete);
        loadThreads();
    }

    function beginDeleteWithUndo(session) {
        threadsList.querySelector(`.thread-row-wrap[data-session-id="${session.session_id}"]`)?.remove();

        pendingDeleteUndone = false;
        undoToastText.textContent = 'Thread deleted';
        undoToast.classList.add('is-shown');
        undoToastBtn.addEventListener('click', onUndoDelete);

        pendingDeleteTimer = setTimeout(async () => {
            undoToast.classList.remove('is-shown');
            undoToastBtn.removeEventListener('click', onUndoDelete);
            if (pendingDeleteUndone) return;
            await reallyDeleteSession(session);
        }, 5000);
    }

    async function reallyDeleteSession(session) {
        const token = K.getAuthToken();
        if (!token) return;

        try {
            const response = await fetch(
                `${K.API_BASE_URL}/api/chat/session/${session.session_id}?token=${encodeURIComponent(token)}`,
                { method: 'DELETE' }
            );
            if (!response.ok) throw new Error(`Server returned ${response.status}`);

            if (session.session_id === K.getSessionId()) {
                K.clearSession();
                activeContext = null;

                const remaining = await fetchThreadsRaw();
                if (remaining.length) {
                    await openThread(remaining[0].session_id);
                }
                else {
                    feed.innerHTML = '';
                    renderEmptyFeedState();
                }
            }

            await loadThreads();
        }

        catch (error) {
            console.error('Failed to delete thread:', error);
            K.toast("We couldn't delete that thread. Please try again.");
            loadThreads();
        }
    }

    async function fetchThreadsRaw() {
        const token = K.getAuthToken();
        if (!token) return [];

        try {
            const response = await fetch(`${K.API_BASE_URL}/api/auth/sessions?token=${encodeURIComponent(token)}`);
            if (!response.ok) return [];
            const data = await response.json();
            return Array.isArray(data.sessions) ? data.sessions : [];
        }
        catch (error) {
            console.error('Failed to load threads:', error);
            return [];
        }
    }

    async function loadThreads() {
        if (!K.getAuthToken()) { threadsList.innerHTML = ''; return; }
        renderThreadsList(await fetchThreadsRaw());
    }

    function highlightCurrentThread() {
        const currentId = K.getSessionId();
        $$('.thread-row-wrap', threadsList).forEach(wrap => {
            const match = wrap.dataset.sessionId === currentId;
            wrap.classList.toggle('is-current', match);
            const row = $('.thread-row', wrap);
            if (match) row.setAttribute('aria-current', 'true');
            else row.removeAttribute('aria-current');
        });
    }

    async function openThread(sessionId) {
        if (sessionId !== K.getSessionId()) {
            setLoading(true);
            K.setSessionId(sessionId);
            activeContext = null;
            hideContextBar();

            const restored = await restoreSession(sessionId);

            if (!restored) {
                feed.innerHTML = '';
                addKindling("We couldn't load that conversation. Please try again.", false);
            }

            setLoading(false);
            highlightCurrentThread();
        }

        closeDrawer();
    }

    function applyCollapsedState() {
        let collapsed = false;
        try { collapsed = localStorage.getItem(SIDEBAR_COLLAPSE_KEY) === 'true'; }
        catch (error) {}

        threadsSidebar.classList.toggle('is-collapsed', collapsed);
        threadsCollapseBtn.hidden = collapsed;
        threadsExpandBtn.hidden = !collapsed;
        threadsCollapseBtn.setAttribute('aria-expanded', String(!collapsed));
    }

    function openDrawer() {
        threadsSidebar.classList.add('is-open');
        threadsBackdrop.hidden = false;
        requestAnimationFrame(() => threadsBackdrop.classList.add('is-visible'));
        document.addEventListener('keydown', onDrawerKeydown);
    }

    function closeDrawer() {
        if (!threadsSidebar.classList.contains('is-open')) return;
        threadsSidebar.classList.remove('is-open');
        threadsBackdrop.classList.remove('is-visible');
        document.removeEventListener('keydown', onDrawerKeydown);
        setTimeout(() => { threadsBackdrop.hidden = true; }, 250);
    }

    function onDrawerKeydown(e) {
        if (e.key === 'Escape') closeDrawer();
    }

    threadsCollapseBtn.addEventListener('click', () => {
        try { localStorage.setItem(SIDEBAR_COLLAPSE_KEY, 'true'); } catch (error) {}
        applyCollapsedState();
    });

    threadsExpandBtn.addEventListener('click', () => {
        try { localStorage.setItem(SIDEBAR_COLLAPSE_KEY, 'false'); } catch (error) {}
        applyCollapsedState();
    });

    threadsMobileToggle.addEventListener('click', openDrawer);
    threadsBackdrop.addEventListener('click', closeDrawer);

    applyCollapsedState();

    async function startConversation(context) {

        setLoading(true);
        feed.innerHTML = '';
        addKindling(null);

        try {

            const response = await fetch(`${K.API_BASE_URL}/api/chat/start`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: K.getAuthToken() })
            });

            if (!response.ok) throw new Error(`Server returned ${response.status}`);

            const data = await response.json();

            if (!data.session_id) throw new Error('No session id received.');

            K.setSessionId(data.session_id);

            feed.innerHTML = '';

            addKindling(data.opening_question || "What have you been curious about lately?", true);

            showOccupationContext(context);

            questionIndex = 0;
            updateProgress();

        }

        catch (error) {
            console.error('Failed to start chat:', error);
            feed.innerHTML = '';
            addKindling("We couldn't start the conversation. Please try again.", false);
        }

        finally {
            setLoading(false);
        }

        /*
         * Kindling always speaks first; the grounded auto-send (if
         * any) is the next real turn, not a race with the opening
         * one — runs only after this function's own setLoading(false)
         * above, so sendMessage()'s own isLoading guard (inside
         * showOccupationContext) doesn't see a stale in-flight state
         * and silently no-op.
         */
        await showOccupationContext(context);

    }

    async function restoreSession(sessionId) {

        try {

            const response = await fetch(`${K.API_BASE_URL}/api/chat/session/${sessionId}?token=${encodeURIComponent(K.getAuthToken())}`);

            if (!response.ok) return false;

            const data = await response.json();

            if (Array.isArray(data.transcript) && data.transcript.length > 0) {
                renderTranscript(data.transcript);
            }

            if (typeof data.user_messages_count === 'number') {
                questionIndex = data.user_messages_count;
            }

            updateProgress();

            return true;

        }

        catch (error) {
            console.error('Failed to restore session:', error);
            return false;
        }

    }

    async function sendMessage(text, opts = {}) {

        text = text.trim();
        if (!text || isLoading) return;

        if (!K.getSessionId()) {
            await startConversation();
            if (!K.getSessionId()) return;
        }

        const sessionId = K.getSessionId();

        addUser(text);
        input.value = '';
        autoGrowInput();
        setLoading(true);

        const pending = addKindling(null);

        try {

            const response = await fetch(`${K.API_BASE_URL}/api/chat/message`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: sessionId,
                    token: K.getAuthToken(),
                    message: text,
                    context: activeContext ? {
                        title: activeContext.title,
                        description: activeContext.description,
                        tasks: activeContext.tasks
                    } : undefined,
                    introRequest: opts.introRequest || undefined
                })
            });

            if (!response.ok) throw new Error(`Server returned ${response.status}`);

            const data = await response.json();

            pending.innerHTML = data.reply ? K.renderMarkdown(data.reply) : '';

            if (typeof data.question_index === 'number') questionIndex = data.question_index;
            if (typeof data.total_questions === 'number') totalQuestions = data.total_questions;

            // Only a real scored completion shows the card - the
            // insufficient-content bailout lands on this same turn
            // (question_index === total_questions) but never scores
            // anything, so it relies on this separate flag rather
            // than the turn numbers alone.
            if (data.intake_complete === true) {
                addCompletionCard();
            }

            updateProgress();
            scrollFeed();

            loadThreads();

        }

        catch (error) {
            console.error('Failed to send message:', error);
            pending.innerHTML = `<p>We couldn't send that. Please try again.</p>`;
        }

        finally {
            setLoading(false);
            input.focus();
        }

    }

    const MAX_COMPOSER_HEIGHT = 160;

    function autoGrowInput() {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, MAX_COMPOSER_HEIGHT) + 'px';
    }

    input.addEventListener('input', () => {
        sendBtn.disabled = isLoading || !input.value.trim();
        autoGrowInput();
    });

    input.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
            e.preventDefault();
            sendMessage(input.value);
        }
    });

    form.addEventListener('submit', e => { e.preventDefault(); sendMessage(input.value); });

    $('#newThread').addEventListener('click', async () => {
        K.clearSession();
        activeContext = null;
        hideContextBar();
        await startConversation();
        await loadThreads();
        closeDrawer();
    });

    K.onRoute.explore = async () => {

        /*
         * Read on EVERY entry, not just the first — a second
         * "Explore this in a conversation" click later in the same
         * session re-fires this route handler too, and needs its new
         * context picked up even though `started` is already true by
         * then. Previously `started` short-circuited before this
         * line ever ran again, so a repeat click silently did
         * nothing at all.
         */
        const context = takeOccupationContext();

        if (started) {
            if (context) {
                activeContext = context;
                await showOccupationContext(context);
            }
            return;
        }
        started = true;

        loadThreads();

        // Kept in activeContext (not just used for the "Continuing
        // from" card) so sendMessage() actually sends it to the
        // backend on every turn of this conversation, not just
        // cosmetically in the UI.
        activeContext = context;

        const existingSessionId = K.getSessionId();

        if (existingSessionId) {
            const restored = await restoreSession(existingSessionId);
            if (restored) {
                await showOccupationContext(context);
                return;
            }
        }

        startConversation(context);

    };

})();