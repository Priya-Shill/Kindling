# Kindling API Documentation

**Base URL:** `https://kindling-backend.onrender.com`  
**Swagger UI:** `https://kindling-backend.onrender.com/docs`  
**Database:** SQLite (`kindling.db`)  
**Backend Owner:** Priya

This document describes the API as implemented in `backend/main.py`. The Swagger UI is generated from the same code and is the authoritative reference for request and response fields.

---

## Authentication

* `POST /api/auth/signup` and `POST /api/auth/login` return `{token, email, name}`. `POST /api/auth/google` does the same for a Google ID token and returns 501 unless `GOOGLE_CLIENT_ID` is set on the server.
* The token is the account's id. It has no expiry or refresh.
* Every session-scoped endpoint takes the token (`token` in the JSON body for POST, `?token=` for GET and DELETE) and checks that it owns the session: 401 for a missing or unknown token, 403 for someone else's session, 404 for an unknown session.
* Login is rate limited to 5 failed attempts per 15 minutes, per IP and per email, in memory.

---

## Database Schema (`kindling.db`)

* **`users`**: `id` (Text, Primary Key), `email` (unique), `password_hash`, `name`, `created_at`.
* **`sessions`**: one chat thread.
  * `session_id` (Text, Primary Key), `created_at`, `user_id`, `title`, `pinned`, `pinned_at`.
* **`messages`**: conversation history.
  * `id` (Integer, Primary Key), `session_id` (Foreign Key), `sender` (`user` or `assistant`), `content`, `timestamp`.
  * `suggested` (0 or 1): 1 when a button sent the message instead of the student typing it. Suggested messages are shown in the chat but excluded from scoring and matching.
* **`events`**: telemetry and state. `id`, `session_id`, `event_type`, `event_data` (JSON), `timestamp`. Scores live here as `score_computed` and `profile_updated` events; pattern decisions as `trait_accepted` / `trait_rejected`.
* **`generated_strings`**: cache of AI-generated text. `cache_key` (Primary Key), `kind`, `value`, `created_at`. Kinds: `career_short_title`, `why_connected`, `try_it`, `career_depth`.
* **`reflection_notes`**: `id`, `user_id`, `session_id`, `note_text`, `created_at`.
* **`reflection_preferences`**: `id`, `note_id`, `user_id`, `kind` (`hide_field`, `focus_field`, `pattern_adjust`, `new_to_them`), `label`, `extra` (JSON), `created_at`.

---

## Endpoints

### Health

| Method | Path | Purpose |
| :--- | :--- | :--- |
| GET | `/` , `/health` | Liveness check |

### Accounts and threads

| Method | Path | Purpose |
| :--- | :--- | :--- |
| POST | `/api/auth/signup` | Create an account (password of at least 8 characters) |
| POST | `/api/auth/login` | Sign in |
| POST | `/api/auth/google` | Sign in with a Google ID token |
| GET | `/api/auth/sessions` | List the account's threads |

### Chat

| Method | Path | Purpose |
| :--- | :--- | :--- |
| POST | `/api/chat/start` | Start a thread; returns `session_id` and the opening question |
| POST | `/api/chat/message` | Send a message; returns the reply |
| GET | `/api/chat/session/{session_id}` | Full transcript |
| POST | `/api/chat/session/{session_id}/pin` | Pin or unpin (at most 5 pinned) |
| DELETE | `/api/chat/session/{session_id}` | Delete a thread |

`POST /api/chat/message` does **not** return scores. Request:

```json
{
  "session_id": "…",
  "token": "…",
  "message": "I organized my notes into a colour-coded folder system",
  "suggested": false
}
```

Optional fields: `context` (`{title, description, tasks}` of the Career Graph occupation the student came from), `introRequest`, and `suggested` (true when a button sent the message).

Response (200 OK):

```json
{
  "reply": "What made you start colour-coding them?",
  "question_index": 3,
  "total_questions": 7,
  "intake_complete": false
}
```

Messages 1 to 7 are the intake. The 7th triggers scoring and returns `intake_complete: true`, unless the answers were too short to score. From the 8th message on, replies are open mentor chat.

### Inference (scores)

| Method | Path | Purpose |
| :--- | :--- | :--- |
| GET | `/api/chat/inference/{session_id}` | The 6 scores. `?scope=all` returns one combined score across all the account's threads |
| GET | `/api/user/profile/{session_id}` | Same scores, without rescoring |
| POST | `/api/user/profile/update` | Overwrite all 6 scores |
| POST | `/api/user/trait/decision` | `accept` or `reject` one dimension. `reject` sets that dimension to `override_value` (default 0.0) and changes no other dimension |

Response of `GET /api/chat/inference/{session_id}`:

```json
{
  "status": "success",
  "session_id": "…",
  "scope": "single",
  "inference": {
    "builds_tinkers": 0.10,
    "investigates_why": 0.30,
    "creates_expresses": 0.15,
    "works_with_people": 0.10,
    "organizes_systems": 0.85,
    "leads_persuades": 0.10
  },
  "inference_failed": false
}
```

In single scope this endpoint also rescores the full transcript when at least 2 new typed messages exist since the last score, unless the student has corrected their profile since then.

### Career Graph

| Method | Path | Purpose |
| :--- | :--- | :--- |
| GET | `/api/career-tree/{session_id}` | The tree: `{nodes, edges}`. `?scope=all` for all threads combined |
| POST | `/api/career-tree/more` | Next layer of occupations for one area or field node ("Show more") |
| GET | `/api/career-depth/{session_id}/{occupation_id}` | "Where this work happens" and "Ways people specialise" for one occupation |
| GET | `/api/chat/explain/{session_id}/{occupation_id}` | SHAP contribution of each dimension to one match, plus a task-based narrative |
| GET | `/api/career-graph/{session_id}` | Older flat list of RIASEC-only matches. Not used by the current frontend |

**Tree nodes.** `type` is `hub`, `area` (a pattern), `field`, or `career`. Field nodes carry `label` (hand-written) and `officialTitle` (BLS). Career nodes carry `soc`, `fullTitle`, `label`, `description`, `tasks`, `why`, and usually `tryIt`. Edges are `branch` or `cross` (with a `reason`). No similarity or score is ever returned.

Occupations are selected by a hybrid ranking of RIASEC fit, local embedding similarity, and a BM25 boost, with no LLM involved. See `Architecture_ rev1.md`.

**`POST /api/career-tree/more`** request:

```json
{
  "session_id": "…",
  "token": "…",
  "scope": "single",
  "node_id": "p:A",
  "shown": ["27-2031.00", "27-2032.00"],
  "fields": ["f:A-27-2"]
}
```

`node_id` is an area (`p:A`) or field (`f:A-27-2`) node id. `shown` is the SOC codes already on the student's map and `fields` the field node ids under that area; the map state lives in the browser. The response is `{nodes, edges, remaining}` to merge into the existing tree. Every returned career is a real dataset occupation. No AI call is made.

**`GET /api/career-depth/...`** response:

```json
{
  "status": "success",
  "occupation_id": "27-2031.00",
  "workplaces": [
    {"setting": "Dance companies and troupes", "examples": ["…", "…"]}
  ],
  "specialisations": [
    {"name": "Ballet", "about": "…"}
  ]
}
```

Generated by one LLM call per occupation, validated, and cached by SOC code for all users. Returns 404 for an occupation that is not in the dataset and 503 (nothing cached) if generation fails. The named examples are AI-generated and are not verified.

### Reflection

| Method | Path | Purpose |
| :--- | :--- | :--- |
| POST | `/api/reflection/note` | Save a "Your take" note (up to 1000 characters); extracts and applies hide, focus, and pattern preferences |
| GET | `/api/reflection/notes` | The account's notes and their preferences |
| DELETE | `/api/reflection/preference/{pref_id}` | Undo one preference |
| DELETE | `/api/reflection/note/{note_id}` | Delete a note and its preferences |

Saving or removing a preference clears that account's cached trees, so the next Career Graph load reflects it.

### Telemetry

| Method | Path | Purpose |
| :--- | :--- | :--- |
| POST | `/api/events/log` | Log a client event (for example `node_time`) |
| GET | `/api/dashboard/timeline/{session_id}` | A thread's events; `?scope=all` for all threads |
| GET | `/api/dashboard/metrics` | Aggregate usage metrics |
| GET | `/api/dashboard/field-summary` | Event counts by type |

---

## Scoring Benchmarks

The scorer's benchmark results are in `AI_Scoring_engine_rev1.md`. They are results of the scoring function on single-answer transcripts, not of an API endpoint: no endpoint returns scores for a single message.
