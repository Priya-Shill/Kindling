# Kindling: Conversational Career Exploration Engine

Kindling is an AI-powered career guidance platform that mines behavioral communication signals from natural student dialogue to map user interests onto a 923-occupation career graph.

Unlike traditional static surveys that rely on self-reported preferences, Kindling evaluates *how* students communicate and what triggers their curiosity across 6 core dimensions.

---

## Team & Roles

* **Aleena (Data Engineering):** O*NET database pipeline processing and the 923-occupation career graph (`Scripts/part_a.py`, `Scripts/part_b.py`, `Outputs/career_graph.json`), including Gaussian Mixture Model (GMM) clustering of occupations into families.
* **Sruthi (AI Core):** Resilient multi-provider LLM wrapper (`ai_core/call_llm.py`) and 6-dimension behavioral scoring engine with prompt-injection defense (`ai_core/inference_prompt.py`).
* **Priya (Backend Engineering):** REST API layer for accounts, sessions, transcripts, and results (`backend/main.py`, `backend/db.py`).
* **Gokul (Frontend & UI):** Interactive student dialogue interface (`frontend/`), designed and prototyped in Figma.

---

## Theoretical Foundations

Kindling's methodology is grounded in four core academic frameworks:

1. **Holland's Theory of Vocational Choice (RIASEC):** Maps personality types to occupational environments. Kindling's 6 dimensions align with Holland's Realistic, Investigative, Artistic, Social, Conventional, and Enterprising types.
2. **Krumboltz's Planned Happenstance Theory:** Recognizes that career paths emerge through dynamic curiosity rather than rigid tests.
3. **Samuelson's Revealed Preference Theory:** Evaluates actual observed choices and speech patterns rather than unreliable self-reported survey answers.
4. **Deci & Ryan's Self-Determination Theory (SDT):** Fosters student autonomy through open-ended dialogue rather than forced-choice questionnaires.

---

## The 6 Behavioral Dimensions

| Dimension | Description | Inspired RIASEC Category |
| :--- | :--- | :--- |
| `builds_tinkers` | Modifies, builds, or takes things apart; hands-on experimentation. | Realistic |
| `investigates_why` | Asks follow-up questions; seeks root-cause understanding. | Investigative |
| `creates_expresses` | Uses creative, artistic, or self-expressive language. | Artistic |
| `works_with_people` | Displays interest in helping, teaching, or connecting. | Social |
| `organizes_systems` | Seeks structure, order, planning, and categorization. | Conventional |
| `leads_persuades` | Displays initiative in leading, convincing, or influencing. | Enterprising |

---

## How It Works

1. **Explore (chat).** A 7-question intake conversation, then open-ended mentor chat. If the answers are too short to score, the intake keeps going, one concrete question at a time, until there is enough. Open chat never starts on a thread with no real result, and the chat never produces a career list of its own: before a result exists it says so, and afterwards it points to the Career Graph.
2. **Inference.** Once the intake has enough to go on (at the 7th answer at the earliest) the transcript is scored into the 6 dimensions (`ai_core/inference_prompt.py`). Later, once at least 2 new typed messages exist, the next visit to Inference rescores the full transcript. Messages sent by a button (a Career Graph prompt, a doubt chip, "Try a small task") are stored but never counted as the student's own words.
3. **Career Graph.** A tree of *You → patterns → fields → careers*, built deterministically from the O*NET dataset and then given AI-written labels and explanations.
4. **Reflection.** Time spent, pattern calibration ("This fits" / "Not quite"), and free-text "Your take" notes that can hide or focus parts of the graph.

Full detail is in [`docs/Architecture_ rev1.md`](docs/Architecture_%20rev1.md).

### Career matching (hybrid)

Which careers appear is decided by code, not by the LLM. Every career node is a real occupation from the 923-occupation O*NET dataset. Ranking combines three signals (`backend/career_tree.py`, `backend/topic_relevance.py`):

* **RIASEC fit.** FAISS cosine similarity between the student's 6 scores and each occupation's O*NET interest profile (`Scripts/matching.py`).
* **Local embedding similarity.** The student's own typed words are compared with each occupation's title, description, and sample tasks using `minishlab/potion-base-8M`, a static embedding model. It is loaded with `tokenizers` + `numpy` only (`backend/local_embedder.py`). No embedding API is called, and no `fastembed`, `model2vec`, or PyTorch is needed at runtime.
* **BM25 lexical boost.** Literal word overlap with the occupation text, applied only where the embedding already agrees, so a coincidental shared word does not promote an unrelated job.

Up to four strong topic matches are selected first, before any quota, so a student who talks about dancing sees *Dancers*. The remaining slots keep the existing diversity rules (18 careers targeted, at most 5 per field, no pattern above half the total). An AI step then writes each career's "why" from a verbatim student quote and removes careers it cannot connect to anything the student said; strong topic matches are kept regardless.

### Career Graph depth

* **Show more** (area and field nodes) adds the next layer of real occupations in the same ranking order: 5 for a field, 6 spread across fields for an area. It is deterministic and makes no AI call.
* **Ways people specialise** (career nodes, on request) shows example specialisations as hollow nodes on dashed lines. They are AI-generated, validated in code, cached per occupation, and labelled as examples. They are not occupations and carry no SOC code.
* **Where this work happens** (career panel) lists kinds of workplace with a few named examples. Panel text only, never nodes. Same cached AI call as the specialisations.

### Field labels

Field nodes use hand-written, student-friendly names for each SOC group (`backend/soc_titles.py`), for example `27-2` → "Performing Arts". They are not AI-generated. The official BLS title is kept on the node and shown in the panel as "Official category".

---

## Tech Stack

* **AI & LLM:** Python, Groq API (`openai/gpt-oss-120b`) with Google GenAI (`gemini-3.6-flash`) as fallback, few-shot prompt engineering. LLMs are used for chat, scoring, and short generated text. They are not used for embeddings.
* **Matching:** FAISS (RIASEC cosine similarity), local static embeddings (`potion-base-8M` via `tokenizers` + NumPy), BM25 implemented in `backend/topic_relevance.py`.
* **Data Science:** O*NET Database, Scikit-Learn (Gaussian Mixture Models, TF-IDF), Pandas, NumPy, SHAP (match explanation endpoint).
* **Backend:** FastAPI + Uvicorn, SQLite (`backend/kindling.db`), `python-dotenv`, bcrypt.
* **Frontend:** Static HTML, CSS, and vanilla JavaScript with SVG maps (`frontend/`), no build step.

---

## Setup

```
git clone https://github.com/Priya-on-loop/Kindling.git
cd Kindling
pip install -r requirements.txt
```

Create a `.env` file in the project root (never commit this, it's already covered by `.gitignore`):

```
GROQ_API_KEY=your_key_here
GEMINI_API_KEY=your_key_here
```

Run the backend from the repo root (several modules open `Outputs/` by relative path):

```
uvicorn backend.main:app --port 8000
```

The frontend is the static site in `frontend/`. Its API address is set in `frontend/js/session.js` (`K.API_BASE_URL`), which points at the deployed backend by default.

### Occupation embeddings

The embedding model files (`Outputs/embedding_model/`) and the precomputed occupation vectors (`Outputs/occupation_embeddings.npz`) are committed, so nothing needs to be built or downloaded to run the app. Rebuild them only if `Outputs/career_graph.json` changes:

```
python Scripts/build_occupation_embeddings.py
```

The script saves after every batch and resumes if interrupted. `pip install model2vec` is only needed to re-export the model files if `Outputs/embedding_model/` is missing, or to run the script's optional cross-check against the Model2Vec library. The backend never imports it.

### Tests

Run from the repo root:

```
python -m unittest Tests.test_topic_selection Tests.test_field_labels Tests.test_career_depth Tests.test_chat_honesty Tests.test_suggested_messages Tests.test_reflection_hide_cache Tests.test_matching Tests.test_shap_explainer
```

These 55 tests make no LLM or network calls (AI calls are mocked). Importing the backend still needs the two API keys to be set, and the tests that use the API create and delete their own rows in the local `backend/kindling.db`.

`Tests/test_career_tree.py` is **not** part of this set. See Known Limitations.

---

## Deployment

* **Backend:** Render, started by the `Procfile` (`uvicorn backend.main:app`), Python 3.11.9 (`runtime.txt`). The free tier has a 512 MB memory limit.
* **Frontend:** GitHub Pages, serving `frontend/`.

**Memory.** Measured on a local Windows machine in a fresh process: about **204 MB** after startup and about **236 MB** peak across repeated Career Graph builds. This has **not yet been measured on Render's Linux environment**, so treat it as an estimate until it is checked there. The figure covers the deterministic tree build; it was not measured while LLM enrichment calls were in flight.

**Vendored embedding model.** `Outputs/embedding_model/` adds about 15 MB to the repository (token embeddings stored as float16, plus the tokenizer). In exchange the backend needs no model download at startup and no embedding API. The file is memory-mapped, and loading it adds roughly 8 MB.

**Timing.** A deterministic tree build takes about 46 ms once the index is loaded (about 360 ms for the first build after startup). The first Career Graph load for a thread is noticeably slower, because the AI-written labels and explanations are generated then. Results are cached afterwards.

---

## Known Limitations

* **Named workplace examples are not verified.** The organisations shown under "Where this work happens" are AI-generated. The prompt asks the model to name only organisations it is certain exist, and the panel labels them as examples, but the code cannot check that a named organisation is real or does that work. The same applies to the wording of example specialisations.
* **Vague conversations get little topic signal.** The embedding model is small and static. Short or under-specified conversations, and topics it represents poorly (in testing, "cricket" and "f1 / i like the cars"), produce weak or slightly off-target topic boosts. Nothing is guaranteed a place in those cases and ranking falls back mostly to RIASEC fit. This is the intended behaviour, but it means the graph is only as specific as what the student wrote.
* **`Tests/test_career_tree.py` is stale.** It predates both the account-token requirement and the rule that tests mock every LLM call: it makes real API calls and is not run as part of normal testing. Tree selection is covered by `Tests/test_topic_selection.py` instead, but the older file's cross-link and structure checks have not been ported, so coverage is not complete.
* **Older sessions can keep an inflated score.** Before button-sent prompts were excluded from scoring, they could raise a dimension the student had shown no evidence for (most visibly Leads & persuades). A session scored under the old behaviour keeps that score until 2 new typed messages trigger a rescore. Sessions where the student pressed "Not quite" are never rescored automatically, so they keep whatever the other dimensions were at that point.
* **The first view can be small.** After the AI relevance step, three real runs kept 5 to 7 of the 18 selected careers. "Show more" is the way to see the rest.
* **In-memory caches.** Built trees and combined-thread scores are cached in process memory and are lost when the backend restarts.

---

## Team

Priya Shill, Sruthi G S, Gokul V S, Aleena Philip Shaji

## Project tracking

Jira dashboard (status overview + Review 1 progress) : https://priyainloop.atlassian.net/jira/dashboards/10003

Jira backlog (full sprint board, all issues) : https://priyainloop.atlassian.net/jira/software/projects/TCP/boards/4/backlog

Deployed Link : https://priya-on-loop.github.io/Kindling/frontend/

## License

MIT License
