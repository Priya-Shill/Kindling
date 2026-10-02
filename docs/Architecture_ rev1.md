# System Architecture & Infrastructure

Kindling is built on a modular 6-layer architecture designed for high uptime, clean separation of concerns, and defensive execution.

---

## 6-Layer Architecture

1. **Frontend Layer (`frontend/`):** Static HTML, CSS, and vanilla JavaScript. Screens for Explore (chat), Inference (radar), Career Graph (SVG tree), Reflection, and Settings. No build step.
2. **Backend / API Layer (`backend/main.py`):** FastAPI app exposing REST endpoints for accounts, chat sessions, inference scores, the career tree, reflection notes, and telemetry.
3. **Persistence Layer (`backend/db.py` / `kindling.db`):** SQLite database storing users, sessions, messages, events (including every score), reflection notes and preferences, and a cache of AI-generated strings.
4. **LLM Execution Layer (`ai_core/call_llm.py`):** Multi-provider LLM wrapper with primary-to-fallback execution.
5. **AI Scoring Engine (`ai_core/inference_prompt.py`):** Formats transcripts into structured few-shot prompts and parses 6D JSON vectors.
6. **Career Graph Engine (`backend/career_tree.py`, `backend/topic_relevance.py`, `backend/tree_enrichment.py`):** Selects real O*NET occupations with a hybrid ranking (RIASEC fit + local embedding similarity + BM25 boost), arranges them into a tree, and adds AI-written labels and explanations.

---

## System Architecture Diagram

```
                        ┌──────────────────────────────────┐
                        │         STUDENT (User)           │
                        └────────────────┬─────────────────┘
                                         │
                                         ▼
                        ┌──────────────────────────────────┐
                        │     FRONTEND LAYER (Gokul)       │
                        │  Static HTML / CSS / JavaScript  │
                        └────────────────┬─────────────────┘
                                         │
                              HTTP REST (JSON)
                                         │
                                         ▼
                        ┌──────────────────────────────────┐
                        │      BACKEND API (Priya)         │
                        │        FastAPI (main.py)         │
                        │  /api/auth/*      /api/chat/*    │
                        │  /api/career-tree/*              │
                        │  /api/career-depth/*             │
                        │  /api/reflection/*  /api/user/*  │
                        └───┬──────────────┬───────────┬───┘
                            │              │           │
              ┌─────────────┘              │           └──────────────┐
              ▼                            ▼                          ▼
 ┌─────────────────────────┐  ┌─────────────────────────┐  ┌──────────────────────────┐
 │  PERSISTENCE LAYER      │  │  AI SCORING ENGINE      │  │  CAREER GRAPH ENGINE     │
 │  SQLite (kindling.db)   │  │  (Sruthi)               │  │  (Aleena: O*NET data)    │
 │                         │  │  inference_prompt.py    │  │                          │
 │  users, sessions,       │  │                         │  │  923 real occupations    │
 │  messages, events,      │  │  6D Interest Vector     │  │  Hybrid ranking:         │
 │  reflection_notes,      │  │  + inference_failed     │──▶  RIASEC fit (FAISS)      │
 │  reflection_preferences,│  │    flag                 │  │  + local embeddings      │
 │  generated_strings      │  └────────────┬────────────┘  │  + BM25 boost            │
 └─────────────────────────┘               │               │  no LLM, no API call     │
                                           │               └────────────┬─────────────┘
                                           ▼                            │
                              ┌─────────────────────────┐               ▼
                              │  LLM WRAPPER (Sruthi)   │  ┌──────────────────────────┐
                              │      call_llm.py        │◀─│  AI ENRICHMENT           │
                              └────────────┬────────────┘  │  short titles, "why",    │
                                           │               │  "try it", career depth  │
                             ┌─────────────┴─────────────┐ │  (cached in SQLite)      │
                             │                           │ └────────────┬─────────────┘
                    (1. Primary)                (2. Fallback)           │
                             ▼                           ▼              ▼
                  ┌──────────────────┐        ┌──────────────────┐  ┌──────────────────┐
                  │     Groq API     │        │    Gemini API    │  │   CAREER TREE    │
                  │  gpt-oss-120b    │        │ gemini-3.6-flash │  │  nodes + edges   │
                  └──────────────────┘        └──────────────────┘  └──────────────────┘
```

The LLM is never asked which careers to show. It scores the conversation, and it writes text for careers the code has already selected.

---

## Conversation and Scoring Flow

* **Phase 1 (intake):** 7 structured questions. Each reply is one short follow-up question; the model is only ever asked for a question here. After the 7th answer the transcript is scored and stored as a `score_computed` event, provided the student's typed answers contain at least 5 distinct content words (stopwords and filler such as "idk" or "yes" don't count). If not, the reply says what kind of answer helps and the intake continues past 7, re-checking after every message, until there is enough.
* **Phase 2 (open mentor chat):** begins only once a real score exists. Sending a message does not score anything. Replies have no fixed template. On every 6th typed message a one-line pointer to the Inference and Career Graph pages is appended in code.
* **No invented results:** the chat never generates a career list as the student's result. Before a score exists, a question like "what career fits me?" gets a fixed honest answer and the next intake question. Once results exist, the mentor is told to point to the Career Graph, and may refer only to the real occupations on the student's graph when that graph has been built.
* **Rescoring:** when the Inference page is requested and at least 2 new typed messages exist since the last score, the full transcript is scored again. It is skipped if the student has since corrected their profile ("Not quite", or a Reflection note), so an automatic rescore never overwrites an explicit correction.
* **Evidence only:** messages sent by a button rather than typed (Career Graph panel prompts, doubt chips, "Try a small task") are flagged `suggested` in the `messages` table. They appear in the chat, but scoring, the rescore count, topic relevance, and the "why" quotes all read the transcript without them. They often contain O*NET task text, which was being scored as the student's own words.

---

## Career Graph Engine

### 1. Which patterns are shown

A dimension becomes an area node if its score is at least 0.25 and the student has not rejected it. One weaker dimension is also shown if the student marked it "This fits".

### 2. Which occupations are selected (hybrid ranking)

Every occupation is assigned to the first of its real O*NET interest high-points that is a shown pattern. Within each pattern, candidates are ordered by:

```
hybrid score = RIASEC fit (z-score) + 1.0 × topic relevance
```

* **RIASEC fit:** FAISS cosine similarity between the student's 6 scores and the occupation's min-max normalized O*NET interest vector (`Scripts/matching.py`), z-scored across all 923 occupations.
* **Topic relevance** (`backend/topic_relevance.py`), computed from the student's own typed words:
  * *Embedding similarity:* cosine between the student's text and each occupation's title + description + sample tasks, using `minishlab/potion-base-8M`. Occupation vectors are precomputed (`Outputs/occupation_embeddings.npz`); the student's text is embedded at request time by the same code (`backend/local_embedder.py`).
  * *BM25 boost:* weight 0.5, applied only to occupations the embedding already places near the student's text (cosine at least 0.35 and at least 2 standard deviations above the mean).
  * *Confidence:* if the best cosine for the whole text is 0.30 or lower there is no topic signal and the order is RIASEC fit alone. It is fully trusted from 0.45.
  * *Vague conversations:* when the whole text is not fully confident, each message is also scored on its own with stricter thresholds, so one clear message ("dancing") is not averaged away by filler.
* **Guaranteed matches:** up to 4 occupations that are clear topic matches are selected before any quota and are exempt from AI pruning.
* **Diversity rules:** 18 careers targeted, at least 2 per pattern where candidates exist, at most 5 per field, and no pattern above half the running total.
* **Connect Threads:** each thread's text is scored separately and the best score per occupation is used.

The embedding model is local. It is read with `tokenizers` + NumPy from two vendored files in `Outputs/embedding_model/`, memory-mapped. There is no embedding API call and no `fastembed`, `model2vec`, or PyTorch dependency at runtime. `Scripts/build_occupation_embeddings.py` exports the model files and builds the occupation vectors, saving after every batch and resuming if interrupted.

### 3. Tree structure and field labels

Selected occupations are grouped into fields by SOC minor group. A group with one member merges into its major group; a field with more than 5 members splits by SOC broad group.

Field labels are hand-written per SOC group in `backend/soc_titles.py`, not AI-generated: every major and minor group in the dataset has one ("27-2" → "Performing Arts"), and 71 broad groups have a more specific one ("Dance", "Music"). Sibling fields never share a label. The official BLS title stays on the node as `officialTitle` and is shown in the panel as "Official category".

### 4. AI enrichment

`backend/tree_enrichment.py` adds, per career: a short map label, a "why it's connected" sentence, and a "try it" activity. The "why" must contain a verbatim quote from the student, checked in code. A career with no such connection is removed from the tree, unless it is a guaranteed topic match. All generated strings are cached in the `generated_strings` table.

### 5. Layered depth

| Feature | Where | Source | AI call |
| :--- | :--- | :--- | :--- |
| Show more | Area and field nodes | Next occupations in the same hybrid ranking: 5 per field, or 6 per area with at most 2 per SOC minor group | None |
| Ways people specialise | Career nodes, on request | Example specialisations, drawn as hollow nodes on dashed lines | One per occupation, cached |
| Where this work happens | Career panel | Kinds of workplace with up to 2 named examples each; text only | Same cached call |

Specialisations and workplaces come from one LLM call per occupation (`ai_core/career_depth.py`), validated in code and cached by SOC code for all users. A failed generation is not cached. The prompt forbids new, emerging, or invented roles. A specialisation has no SOC code and can only hang under a real career.

### 6. Occupation families (GMM)

`Scripts/part_b.py` clusters occupations into 10 families with a Gaussian Mixture Model and stores the result as `family` in `Outputs/career_graph.json`. The Career Graph tree does not use it; fields come from SOC groups. It is returned only by the older `GET /api/career-graph/{session_id}` endpoint, which the current frontend does not call.

---

## LLM Resilience & Fallback Engine

To guarantee zero downtime during API outages or rate limits, the LLM client executes an automatic failover strategy:

```
       ┌────────────────────────┐
       │  User Dialogue Input   │
       └───────────┬────────────┘
                   │
                   ▼
       ┌────────────────────────┐
       │      Backend API       │
       └───────────┬────────────┘
                   │
                   ▼
       ┌────────────────────────┐
       │      call_llm.py       │
       └───────────┬────────────┘
                   │
         ┌─────────┴─────────┐
         │                   │
    (1. Primary)     (2. Fallback on Error)
         │                   │
         ▼                   ▼
    ┌─────────────────┐ ┌───────────────────┐
    │    Groq API     │ │    Gemini API     │
    │ (gpt-oss-120b)  │ │(gemini-3.6-flash) │
    └────────┬────────┘ └─────────┬─────────┘
             │      (Success)     │
             └─────────┬──────────┘
                       │
                       ▼
           ┌────────────────────────┐
           │  Return Output String  │
           └────────────────────────┘
```

If both providers fail, `call_llm` raises and each caller applies its own fallback (a neutral score flagged as failed, a plain apology in chat, an uncached 503 for career depth).

---

## Deployment & Memory

* Backend on Render (`Procfile`: `uvicorn backend.main:app`, Python 3.11.9). Free tier limit: 512 MB.
* Measured locally on Windows in a fresh process: about 204 MB after startup, about 236 MB peak across repeated tree builds. **Not yet measured on Render's Linux environment.**
* `shap` is imported only inside the explain endpoint; importing it at startup cost about 65 MB.
* The vendored embedding model adds about 15 MB to the repository and removes any runtime model download.
* A deterministic tree build takes about 46 ms once the index is loaded. AI enrichment of a new tree is noticeably slower and is cached afterwards.

---

## Core Technical Principles
* **Fail Loud, Not Silent:** If LLM inference fails twice, return neutral scores with `"inference_failed": true`.
* **Injection Resistance:** Treat all user input inside transcripts strictly as data, never as executable commands.
* **Schema Validation:** Enforce strict float checks (0.0 to 1.0) on all 6 required dimension keys.
* **The Data Decides the Structure:** Every career node is a real O*NET occupation chosen by code. AI only names and explains, and anything it generates that could look like a career is labelled as an example.
* **Only the Student's Own Words Are Evidence:** Button-sent prompts are excluded from scoring and matching.

---

## Known Limitations

* Named workplace examples are AI-generated and cannot be verified by the code to be real organisations.
* Vague or under-specified conversations, and topics the small embedding model represents poorly, get weak topic boosts and fall back mostly to RIASEC matching.
* `Tests/test_career_tree.py` is stale: it makes real LLM calls, predates the account-token requirement, and is not run in normal testing.
* Sessions scored before button prompts were excluded keep any inflated score until 2 new typed messages trigger a rescore.

See the README for the full list.
