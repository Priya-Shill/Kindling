"""
Career Graph Phase 2 orchestration: takes Phase 1's deterministic
tree (career_tree.build_career_tree) and fills in the AI-generated
display strings — field short names, career short titles, "why it's
connected", and "try it out" — via ai_core/tree_naming.py, caching
each in the generated_strings table (backend/db.py) so repeat visits
are stable and cheap, exactly per Part E rule 7 of the master prompt.

Field names, career short titles, and "try it" text are session-
independent (the same real occupation/task always gets the same
treatment) and cached globally by occupation/task/field code alone.
"why it's connected" depends on a specific user's real evidence, so
its cache key includes a hash of that evidence.

Cache hits are read synchronously first (cheap local reads); only
genuine cache misses dispatch a real LLM call, and those independent
calls run concurrently — a cold cache of ~60 calls took ~220s run
sequentially in testing, which isn't a reasonable wait for a live
page load. This is still Phase 2's own orchestration, not a Phase 3
API concern.
"""

import sys
import json
import hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent
sys.path.append(str(BACKEND_DIR))
sys.path.append(str(ROOT_DIR / "ai_core"))

from db import get_cached_string, set_cached_string
from tree_naming import (
    generate_career_short_title,
    generate_why_connected,
    generate_try_it,
)

# 10 concurrent workers blew straight through this Groq account's
# real 8000 TPM rate limit in testing (~700-900 tokens/call), so
# almost every call fell back to Gemini instead of actually using
# Groq concurrently. 3 stays comfortably under that ceiling while
# still meaningfully beating fully sequential calls.
MAX_WORKERS = 3

# Real, existing copy from frontend/js/patterns.js — reused here for
# area-node evidence text, not re-generated.
AXIS_DESCRIPTIONS = {
    "builds_tinkers": "You tend to explore by making, testing, and changing something to see what happens.",
    "investigates_why": "You often go past the first answer and look for the reason behind how something works.",
    "creates_expresses": "Your exploration sometimes moves toward creating, communicating, or expressing an idea.",
    "works_with_people": "Some of your exploration involves understanding, helping, or collaborating with others.",
    "organizes_systems": "You show interest in bringing structure to information, processes, and connected pieces.",
    "leads_persuades": "Some activities suggest curiosity about influencing ideas, decisions, or direction.",
}

LETTER_TO_AXIS = {"R": "builds_tinkers", "I": "investigates_why", "A": "creates_expresses",
                   "S": "works_with_people", "C": "organizes_systems", "E": "leads_persuades"}


def _user_evidence_text(messages: list[dict]) -> str:
    user_lines = [m["content"] for m in messages if m["role"] == "user"]
    return "\n".join(user_lines)[:3000]


def _why_connected_job(title: str, desc: str, evidence: str, pattern_label: str) -> str:
    """Wraps generate_why_connected's (why, relevant) tuple as a JSON
    string so it can go through the same generic cache-and-apply job
    machinery as every other (plain-string) generated field."""
    why, relevant = generate_why_connected(title, desc, evidence, pattern_label)
    return json.dumps({"why": why, "relevant": relevant})


def _apply_why(node: dict, value: str) -> None:
    data = json.loads(value)
    node["why"] = data["why"]
    node["relevant"] = data["relevant"]


def _prune_irrelevant_careers(tree: dict) -> dict:
    """
    Drops career nodes whose only real link to the student is the
    broad RIASEC-style pattern (node["relevant"] is False), regardless
    of how well they scored on RIASEC/FAISS similarity - a real
    student quote is now required, not just a personality-pattern
    overlap. A field or area that loses every one of its children this
    way is a dead end and gets dropped too, same "don't show an empty
    branch" rule career_tree.py already applies to patterns with zero
    real candidates in the first place.
    """
    keep_ids = {n["id"] for n in tree["nodes"] if n["type"] != "career" or n.get("relevant", True)}
    nodes = [n for n in tree["nodes"] if n["id"] in keep_ids]
    edges = [e for e in tree["edges"] if e["source"] in keep_ids and e["target"] in keep_ids]

    changed = True
    while changed:
        changed = False
        children_of = {}
        for e in edges:
            if e["kind"] == "branch":
                children_of.setdefault(e["source"], []).append(e["target"])
        for n in list(nodes):
            if n["type"] in ("field", "area") and not children_of.get(n["id"]):
                dead_id = n["id"]
                nodes = [x for x in nodes if x["id"] != dead_id]
                edges = [e for e in edges if e["source"] != dead_id and e["target"] != dead_id]
                changed = True

    if len(nodes) <= 1:
        return {"nodes": [{"id": "you", "type": "hub", "label": "You"}], "edges": []}

    for n in nodes:
        n.pop("relevant", None)

    return {"nodes": nodes, "edges": edges}


def _run_job(job):
    cache_key, kind, generate_fn, apply_fn = job
    value = generate_fn()
    set_cached_string(cache_key, kind, value)
    return apply_fn, value


def enrich_tree_with_ai(tree: dict, messages: list[dict]) -> dict:
    """
    messages is whatever real transcript this tree was actually built
    from - one session's (existing single-thread behavior) or a
    Connect Threads combined transcript across every real session -
    used only to write evidence-grounded "why" copy; the enrichment
    cache itself is keyed by its content hash either way, so combined
    and single-session enrichment never collide or overwrite the
    other's cached copy for the same occupation.
    """
    evidence_text = _user_evidence_text(messages)
    evidence_hash = hashlib.sha256(evidence_text.encode("utf-8")).hexdigest()[:16]

    nodes_by_id = {n["id"]: n for n in tree["nodes"]}

    jobs = []  # (cache_key, kind, generate_fn, apply_fn) — real cache misses only

    for node in tree["nodes"]:

        if node["type"] == "area":
            axis = LETTER_TO_AXIS.get(node["riasec"])
            node["why"] = AXIS_DESCRIPTIONS.get(axis, "")

        # Field nodes' "label" is already the real, hand-written
        # display name from soc_titles.field_display_label() (see
        # career_tree.py) - no AI call needed or made for it.

        elif node["type"] == "career":
            soc = node["soc"]

            short_key = f"short_title:{soc}"
            cached = get_cached_string(short_key)
            if cached is not None:
                node["label"] = cached
            else:
                jobs.append((
                    short_key, "career_short_title",
                    lambda title=node["fullTitle"]: generate_career_short_title(title),
                    lambda value, n=node: n.__setitem__("label", value),
                ))

            why_key = f"why:{soc}:{evidence_hash}"
            cached = get_cached_string(why_key)
            if cached is not None:
                cached_data = json.loads(cached)
                node["why"] = cached_data["why"]
                node["relevant"] = cached_data["relevant"]
            else:
                field_node = nodes_by_id.get(node["parent"])
                area_node = nodes_by_id.get(field_node["parent"]) if field_node else None
                pattern_label = area_node["label"] if area_node else "what you've explored"

                jobs.append((
                    why_key, "why_connected",
                    lambda title=node["fullTitle"], desc=node.get("description", ""), pat=pattern_label:
                        _why_connected_job(title, desc, evidence_text, pat),
                    lambda value, n=node: _apply_why(n, value),
                ))

            task_ids = node.get("taskIds", [])
            task_texts = node.get("tasks", [])
            if task_ids and task_texts:
                first_task_id = task_ids[0]
                first_task_text = task_texts[0]
                tryit_key = f"tryit:{first_task_id}"
                cached = get_cached_string(tryit_key)
                if cached is not None:
                    node["tryIt"] = {"text": cached, "sourceTaskId": first_task_id}
                else:
                    def _make_apply(n, task_id):
                        return lambda value: n.__setitem__("tryIt", {"text": value, "sourceTaskId": task_id})

                    jobs.append((
                        tryit_key, "try_it",
                        lambda title=node["fullTitle"], task=first_task_text: generate_try_it(title, task),
                        _make_apply(node, first_task_id),
                    ))

    if jobs:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(_run_job, job) for job in jobs]
            for future in as_completed(futures):
                apply_fn, value = future.result()
                apply_fn(value)

    return _prune_irrelevant_careers(tree)
