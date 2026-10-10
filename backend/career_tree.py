"""
Deterministic Career Graph tree builder (Phase 1 of the star->tree
rebuild). No AI calls happen here — see Part C of the master prompt:
"The data decides the structure. The AI only names and explains."
Node labels that a later AI-naming pass (Phase 2) will shorten are
set to their real, full, non-fabricated title as an honest
placeholder (a real full O*NET title or a real official BLS SOC
group title), never invented text.
"""

import sys
import csv
import math
from pathlib import Path
from collections import defaultdict

BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent
sys.path.append(str(BACKEND_DIR))
sys.path.append(str(ROOT_DIR / "Scripts"))

from db import get_latest_inference_scores, get_latest_trait_decisions, get_session_user_id, get_active_reflection_preferences, get_messages
from soc_titles import major_group, minor_group, broad_group, major_title, minor_title, field_display_label
from matching import match_occupations, load_career_graph, RIASEC_COLUMNS
from topic_relevance import topic_relevance

INTEREST_TYPES_PATH = str(ROOT_DIR / "Data" / "career_interest_types.csv")

# Real O*NET RIASEC <-> Kindling axis naming (Scripts/part_a.py's own
# rename when it built Outputs/riasec_wide.csv from the real
# Occupational Interest scale) — reused here, not re-derived.
AXIS_TO_LETTER = {
    "builds_tinkers": "R",
    "investigates_why": "I",
    "creates_expresses": "A",
    "works_with_people": "S",
    "organizes_systems": "C",
    "leads_persuades": "E",
}
LETTER_TO_AXIS = {v: k for k, v in AXIS_TO_LETTER.items()}

# Real, existing copy from frontend/js/patterns.js — not re-invented
# here, just made available server-side for area-node labels.
AXIS_LABELS = {
    "builds_tinkers": "Build & tinker",
    "investigates_why": "Investigates why",
    "creates_expresses": "Create & express",
    "works_with_people": "Works with people",
    "organizes_systems": "Organizes systems",
    "leads_persuades": "Leads & persuades",
}

RIASEC_CODE_TO_LETTER = {1: "R", 2: "I", 3: "A", 4: "S", 5: "E", 6: "C"}

EVIDENCE_THRESHOLD = 0.25  # matches frontend/js/inference.js's own "Starting to appear" band
TARGET_LEAF_COUNT = 18
MIN_LEAVES = 15
MAX_LEAVES = 24
MIN_PER_PATTERN = 2
MAX_PER_FIELD = 5
MAX_PATTERN_SHARE = 0.5
MAX_CROSSLINKS_PER_NODE = 2
MAX_CROSSLINKS_TOTAL = 12

# "Show more" occupations get a plain, honest reason instead of an AI
# "why" call: the student asked for more, nothing they said is being
# quoted. One wording when the work is clearly about what they've been
# saying (topic score, see topic_relevance), one when it only shares
# the pattern.
MORE_ON_TOPIC_SCORE = 3.0
MORE_WHY_ON_TOPIC = "This is closely related to what you've been talking about."
MORE_WHY_PATTERN = "This shares the {pattern} pattern with what you've explored. You asked to see more here."

# Hybrid ranking: RIASEC fit and topic relevance are both expressed as
# z-scores over the whole dataset, so a weight of 1 lets an occupation
# that is clearly about what the student said (topic ~ +3) outrank one
# that only shares their RIASEC shape (fit ~ +1.5 for a very good
# match), while RIASEC still orders everything the student's words say
# nothing about.
TOPIC_WEIGHT = 1.0


def load_interest_high_points() -> dict:
    """
    {soc_id: ["I", "C", ...]} — the real, ordered First/Second/Third
    Interest High-Points (Data/career_interest_types.csv, Element IDs
    1.B.1.g/h/i, Scale ID 'IH'), standard O*NET 1-6 RIASEC coding.
    A Data Value of 0.00 is O*NET's own "no distinct high point at
    this rank" marker and is skipped (0 isn't a valid RIASEC code).
    """
    raw = defaultdict(dict)
    with open(INTEREST_TYPES_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rank_by_name = {
            "First Interest High-Point": 1,
            "Second Interest High-Point": 2,
            "Third Interest High-Point": 3,
        }
        for row in reader:
            if row["Scale ID"] != "IH":
                continue
            rank = rank_by_name.get(row["Element Name"])
            if rank is None:
                continue
            raw[row["O*NET-SOC Code"]][rank] = float(row["Data Value"])

    result = {}
    for soc_id, ranks in raw.items():
        ordered = []
        for rank in (1, 2, 3):
            code = int(ranks.get(rank, 0.0))
            if code in RIASEC_CODE_TO_LETTER:
                ordered.append(RIASEC_CODE_TO_LETTER[code])
        result[soc_id] = ordered
    return result


def field_title(field_code: str) -> str:
    """Real official BLS SOC title at whatever granularity field_code
    actually is: 2-char major, 4-char minor, or 6-char broad (which
    uses its parent minor group's real title — BLS doesn't publish
    separate broad-group names)."""
    if len(field_code) == 2:
        return major_title(field_code)
    if len(field_code) == 4:
        return minor_title(field_code)
    return minor_title(field_code[:4])


def determine_shown_patterns(scores: dict, decisions: dict) -> list:
    """
    Level 1. Never show a trait marked "Not quite" (reject). Show
    every trait with real evidence (score >= EVIDENCE_THRESHOLD) that
    hasn't been rejected. At most one additional trait below that
    threshold is let through if explicitly marked "This fits"
    (accept) — the highest-scoring such trait, since the rule caps
    this at one regardless of how many were accepted.
    """
    strong = [
        axis for axis in AXIS_LABELS
        if scores.get(axis, 0.0) >= EVIDENCE_THRESHOLD and decisions.get(axis) != "reject"
    ]

    weak_accepted = [
        axis for axis in AXIS_LABELS
        if axis not in strong and decisions.get(axis) == "accept"
    ]
    if weak_accepted:
        weak_accepted.sort(key=lambda a: scores.get(a, 0.0), reverse=True)
        strong.append(weak_accepted[0])

    strong.sort(key=lambda a: (-scores.get(a, 0.0), list(AXIS_LABELS).index(a)))
    return strong


def assign_pattern(soc_id: str, shown_patterns: list, high_points: dict):
    """Level 3: the first of this occupation's real IH high-points
    (First, then Second, then Third) that's among the shown patterns.
    None if none match — the caller drops the occupation rather than
    force-assigning it somewhere dishonest."""
    shown_letters = {AXIS_TO_LETTER[a] for a in shown_patterns}
    for letter in high_points.get(soc_id, []):
        if letter in shown_letters:
            return LETTER_TO_AXIS[letter]
    return None


def group_into_fields(occupations: list) -> dict:
    """
    Level 2: group by real SOC minor group (first 4 chars of the
    O*NET-SOC code). A minor group with exactly one member merges up
    into its major group. Any resulting field with more than
    MAX_PER_FIELD members splits by broad group (first 6 chars); a
    broad-group split that would leave a singleton merges back into
    the ORIGINAL (pre-split) field instead of escalating further
    (approved deviation — avoids scattering a lone occupation into an
    unrelated major-level bucket).
    Returns {field_code: [occupations]}.
    """
    by_minor = defaultdict(list)
    for occ in occupations:
        by_minor[minor_group(occ["id"])].append(occ)

    fields = {}
    singleton_minors_by_major = defaultdict(list)
    for minor, occs in by_minor.items():
        if len(occs) == 1:
            singleton_minors_by_major[major_group(minor)].extend(occs)
        else:
            fields[minor] = occs
    for major, occs in singleton_minors_by_major.items():
        fields.setdefault(major, []).extend(occs)

    split_fields = {}
    for field_code, occs in fields.items():
        if len(occs) <= MAX_PER_FIELD:
            split_fields[field_code] = occs
            continue

        by_broad = defaultdict(list)
        for occ in occs:
            by_broad[broad_group(occ["id"])].append(occ)

        leftover_singletons = []
        for broad, broad_occs in by_broad.items():
            if len(broad_occs) == 1:
                leftover_singletons.extend(broad_occs)
            else:
                split_fields[broad] = broad_occs

        if leftover_singletons:
            split_fields.setdefault(field_code, []).extend(leftover_singletons)

    return split_fields


def field_labels(fields: dict) -> dict:
    """
    {field_code: display label} for one area's fields (the output of
    group_into_fields). Sibling fields never share a label: a minor
    group split by broad group would otherwise show the same name two
    or three times ("Performing Arts" for dance, music and acting
    alike). A broad field with no label of its own is named after the
    occupations in it; the leftover minor-level field becomes "Other".
    """
    labels = {
        code: field_display_label(code, [occ["id"] for occ in occs])
        for code, occs in fields.items()
    }
    seen = defaultdict(int)
    for label in labels.values():
        seen[label] += 1

    for code, occs in fields.items():
        label = labels[code]
        if seen[label] < 2:
            continue
        if len(code) == 6:
            shortest = sorted((occ["title"] for occ in occs), key=len)[:2]
            labels[code] = " & ".join(shortest)
        elif not label.startswith("Other"):
            labels[code] = f"Other {label}"
    return labels


def rank_patterns(all_occs_by_id: dict, scores: dict, shown_patterns: list, high_points: dict,
                   evidence_text="") -> tuple:
    """
    Ranks the real candidate pool once and buckets every real
    candidate under its Level-3-assigned pattern, best first - the
    shared input both select_occupations (the default first view) and
    more_occupations ("Show more") build on, so "more" always
    continues the exact same order the first view was drawn from
    rather than deriving a different one.

    The order is a hybrid of two things, neither ever returned to the
    UI: RIASEC fit (FAISS cosine similarity to the student's scores)
    and topic relevance to the student's own words (backend/
    topic_relevance.py - local embeddings plus a BM25 lexical boost).
    RIASEC alone ranked obvious matches ("Dancers" for a dancing-only
    student) just outside a small per-pattern quota on vector-geometry
    noise. With no usable evidence the order is RIASEC fit alone.

    Returns (buckets, guaranteed_ids). guaranteed_ids are the few
    strong topic matches that must reach the first view; each sits at
    the front of its bucket.

    Rank the ENTIRE real dataset, not an arbitrary top-N slice: a
    secondary shown pattern's honest matches often rank lower in
    *overall* 6D similarity (that's dominated by the student's
    strongest axes) even though they're a perfectly real match for
    that specific pattern's own IH high-point. Truncating the pool
    early was silently starving weaker-but-shown patterns of real
    candidates that do exist further down the ranking — confirmed
    by testing (see career-tree test run notes).
    """
    student_vector = [scores.get(col, 0.0) for col in RIASEC_COLUMNS]
    pool_size = len(all_occs_by_id)
    ranked = match_occupations(
        student_vector, threshold=0.0,
        max_results=pool_size, min_results=pool_size,
    )

    topic, strong_ids = topic_relevance(evidence_text)
    guaranteed_ids = {occ_id for occ_id in strong_ids if occ_id in all_occs_by_id}

    similarities = [m["similarity"] for m in ranked]
    mean = sum(similarities) / len(similarities) if similarities else 0.0
    spread = math.sqrt(sum((s - mean) ** 2 for s in similarities) / len(similarities)) if similarities else 0.0

    hybrid = {}
    buckets = {p: [] for p in shown_patterns}
    for m in ranked:
        occ = all_occs_by_id.get(m["id"])
        if not occ:
            continue
        pattern = assign_pattern(m["id"], shown_patterns, high_points)
        if pattern is None and m["id"] in guaranteed_ids:
            # None of this occupation's top-three interests is a shown
            # pattern, but the student is plainly talking about this
            # work - place it under whichever shown pattern the
            # occupation's own real RIASEC profile is strongest on.
            pattern = max(shown_patterns, key=lambda p: occ["riasec"][p])
        if pattern in buckets:
            fit = (m["similarity"] - mean) / spread if spread else 0.0
            hybrid[m["id"]] = fit + TOPIC_WEIGHT * topic.get(m["id"], 0.0)
            buckets[pattern].append(occ)

    for pattern in buckets:
        buckets[pattern].sort(key=lambda occ: (occ["id"] not in guaranteed_ids, -hybrid[occ["id"]]))

    return buckets, guaranteed_ids


# "Show more" reveals one layer per click. A field's layer is simply
# its next few occupations; an area's layer is spread across fields
# (at most MORE_AREA_MAX_PER_FIELD from any one SOC minor group) so a
# single large field can't take over the layer.
MORE_FIELD_BATCH = 5
MORE_AREA_BATCH = 6
MORE_AREA_MAX_PER_FIELD = 2


def more_occupations(scores: dict, shown_patterns: list, high_points: dict,
                      hidden_ids: frozenset, hidden_field_codes: frozenset, evidence_text,
                      pattern: str, already_selected_ids: set, field_code: str = None) -> list:
    """
    Every real candidate not yet shown for a "Show more" click on a
    field or pattern/area node, best first - continues the exact same
    ranking (RIASEC fit + dataset-wide topic relevance) the first view
    was drawn from, rather than a separate relevance pass, so "more"
    never contradicts what's already shown. field_code narrows to one
    field within the pattern; None means the whole pattern/area, which
    can surface fields not present in the default view at all.

    Deliberately goes past MAX_PER_FIELD once a student explicitly
    asks for more - that cap exists to keep the unsolicited first view
    balanced, not to cap how many real matches exist for a field.
    """
    all_occs_by_id = {
        occ["id"]: occ for occ in load_career_graph()
        if occ["id"] not in hidden_ids
        and minor_group(occ["id"]) not in hidden_field_codes
        and major_group(occ["id"]) not in hidden_field_codes
        and broad_group(occ["id"]) not in hidden_field_codes
    }
    buckets, _ = rank_patterns(all_occs_by_id, scores, shown_patterns, high_points, evidence_text)
    bucket = buckets.get(pattern, [])

    if field_code:
        def in_field(occ_id):
            return (minor_group(occ_id) == field_code
                    or major_group(occ_id) == field_code
                    or broad_group(occ_id) == field_code)
        bucket = [occ for occ in bucket if in_field(occ["id"])]

    return [occ for occ in bucket if occ["id"] not in already_selected_ids]


def career_node(occ: dict, parent_id: str) -> dict:
    sample_tasks = occ.get("sample_tasks", [])
    return {
        "id": f"o:{occ['id']}", "type": "career",
        "label": occ["title"], "fullTitle": occ["title"],
        "soc": occ["id"], "parent": parent_id,
        "description": occ.get("description", ""),
        "tasks": [t["text"] for t in sample_tasks],
        "taskIds": [t["task_id"] for t in sample_tasks],
    }


def build_more_nodes(scores: dict, decisions: dict, hidden_ids: frozenset, hidden_field_codes: frozenset,
                      evidence_text, node_id: str, shown_ids: set, existing_field_ids: set) -> dict:
    """
    The next layer for a "Show more" click on an area ("p:A") or field
    ("f:A-27-2") node: {"nodes", "edges", "remaining"} to merge into
    the tree the student already has. Only real occupations from the
    dataset, in the same order the first view used.

    A field's layer attaches to that field. An area's layer attaches
    each occupation to the matching field already on the map, or to a
    new field node for its SOC minor group.
    """
    empty = {"nodes": [], "edges": [], "remaining": 0}

    kind, _, rest = node_id.partition(":")
    letter, field_code = rest[:1], rest[2:] or None
    pattern = LETTER_TO_AXIS.get(letter)
    if kind not in ("p", "f") or pattern is None or (kind == "f") != bool(field_code):
        return empty

    shown_patterns = determine_shown_patterns(scores, decisions)
    if pattern not in shown_patterns:
        return empty

    candidates = more_occupations(
        scores, shown_patterns, load_interest_high_points(), hidden_ids, hidden_field_codes,
        evidence_text, pattern, shown_ids, field_code,
    )

    if field_code:
        batch = candidates[:MORE_FIELD_BATCH]
    else:
        batch, per_field = [], defaultdict(int)
        for occ in candidates:
            minor = minor_group(occ["id"])
            if per_field[minor] >= MORE_AREA_MAX_PER_FIELD:
                continue
            per_field[minor] += 1
            batch.append(occ)
            if len(batch) == MORE_AREA_BATCH:
                break

    topic, _ = topic_relevance(evidence_text)
    area_id = f"p:{letter}"
    nodes, edges, new_fields = [], [], {}

    for occ in batch:
        if field_code:
            parent_id = node_id
        else:
            broad_id = f"f:{letter}-{broad_group(occ['id'])}"
            minor_id = f"f:{letter}-{minor_group(occ['id'])}"
            parent_id = broad_id if broad_id in existing_field_ids else minor_id
            if parent_id not in existing_field_ids:
                new_fields.setdefault(parent_id, []).append(occ["id"])

        node = career_node(occ, parent_id)
        node["why"] = (
            MORE_WHY_ON_TOPIC if topic.get(occ["id"], 0.0) >= MORE_ON_TOPIC_SCORE
            else MORE_WHY_PATTERN.format(pattern=AXIS_LABELS[pattern])
        )
        nodes.append(node)
        edges.append({"source": parent_id, "target": node["id"], "kind": "branch"})

    for field_id, member_ids in new_fields.items():
        code = field_id[4:]
        nodes.insert(0, {
            "id": field_id, "type": "field",
            "label": field_display_label(code, member_ids), "officialTitle": field_title(code),
            "parent": area_id,
        })
        edges.insert(0, {"source": area_id, "target": field_id, "kind": "branch"})

    return {"nodes": nodes, "edges": edges, "remaining": len(candidates) - len(batch)}


def select_occupations(scores: dict, shown_patterns: list, high_points: dict,
                        hidden_ids: frozenset = frozenset(), hidden_field_codes: frozenset = frozenset(),
                        evidence_text=""):
    """
    Ranks the real candidate pool once (rank_patterns - hybrid of
    RIASEC fit and topic relevance, kept internal/never returned to
    the UI), buckets each real candidate under its Level-3-assigned
    pattern, then greedily fills each pattern honoring: >=MIN_PER_PATTERN where real
    candidates allow it, no single field ever exceeding MAX_PER_FIELD
    (checked by actually re-running the Level-2 grouping on every
    trial addition), and no pattern exceeding MAX_PATTERN_SHARE of the
    running total. Never fabricates a candidate to hit a quota.

    hidden_ids/hidden_field_codes are real per-user preferences from
    Reflection's "Your take" notes (see db.get_active_reflection_
    preferences) - excluded from the candidate pool itself, so a
    hidden occupation/field can never be selected in the first place,
    same as if it didn't exist in the dataset.

    evidence_text is the student's own real words (Phase 1 intake +
    typed Phase 2 chat) - one string, or one per thread in Connect
    Threads' combined mode. The few strong topic matches rank_patterns
    reports are selected first, before any quota is applied, so an
    occupation the student is plainly talking about always reaches the
    first view; they still respect MAX_PER_FIELD and never create a
    pattern that isn't already shown.
    """
    all_occs_by_id = {
        occ["id"]: occ for occ in load_career_graph()
        if occ["id"] not in hidden_ids
        and minor_group(occ["id"]) not in hidden_field_codes
        and major_group(occ["id"]) not in hidden_field_codes
        and broad_group(occ["id"]) not in hidden_field_codes
    }

    buckets, guaranteed_ids = rank_patterns(all_occs_by_id, scores, shown_patterns, high_points, evidence_text)

    selected_by_pattern = {p: [] for p in shown_patterns}
    cursor = {p: 0 for p in shown_patterns}

    def total_selected():
        return sum(len(v) for v in selected_by_pattern.values())

    def try_add(pattern):
        while cursor[pattern] < len(buckets[pattern]):
            candidate = buckets[pattern][cursor[pattern]]
            cursor[pattern] += 1
            trial = selected_by_pattern[pattern] + [candidate]
            if all(len(v) <= MAX_PER_FIELD for v in group_into_fields(trial).values()):
                selected_by_pattern[pattern].append(candidate)
                return True
        return False

    for pattern in shown_patterns:
        # Guaranteed matches sit at the front of their bucket.
        while cursor[pattern] < len(buckets[pattern]) and buckets[pattern][cursor[pattern]]["id"] in guaranteed_ids:
            try_add(pattern)

    for pattern in shown_patterns:
        while len(selected_by_pattern[pattern]) < MIN_PER_PATTERN:
            if not try_add(pattern):
                break

    stalled = set()
    while total_selected() < TARGET_LEAF_COUNT and len(stalled) < len(shown_patterns):
        progressed = False
        for pattern in shown_patterns:
            if pattern in stalled or total_selected() >= TARGET_LEAF_COUNT:
                continue
            prospective_total = total_selected() + 1
            # Ceiling, not a strict fractional cap: with few shown
            # patterns (e.g. 2, each already at parity), a strict "> 0.5
            # of prospective_total" check blocks BOTH patterns on the
            # exact same round forever - (2+1) > 0.5*5 is true for every
            # pattern simultaneously, so neither ever grows past 2 even
            # with 60+ real candidates still sitting in the bucket
            # (found while verifying real students never got real
            # occupations like Musicians and Singers surfaced at all,
            # regardless of the topic-relevance filter above it - this
            # was blocking the candidate before that filter ever ran).
            # Rounding the allowed share up still caps runaway
            # domination by one pattern, it just doesn't deadlock at
            # small integer counts.
            if len(shown_patterns) > 1 and (len(selected_by_pattern[pattern]) + 1) > math.ceil(MAX_PATTERN_SHARE * prospective_total):
                continue
            if try_add(pattern):
                progressed = True
            else:
                stalled.add(pattern)
        if not progressed:
            break

    all_selected = [occ for occs in selected_by_pattern.values() for occ in occs]
    return selected_by_pattern, all_selected


# A student's real "focus this field" note explicitly asks to bypass
# the normal MAX_PER_FIELD cap for that one field - these are the
# real caps on how far that bypass goes.
FOCUS_EXTRA_CAP = 4
FOCUS_EXTRA_CAP_DEEP = 8


def nearest_by_task_similarity(seed_occs: list, candidates: list, n: int) -> list:
    """
    Real-data-only fallback for expand_focus_field when a focused
    field's own SOC group is exhausted: ranks `candidates` by TF-IDF
    cosine similarity between their own real sample_tasks text and
    the focused field's real sample_tasks text. This is
    career_tree.py's Rule-2 "task-embedding similarity" (deferred at
    the top of compute_cross_links pending real embeddings) filled in
    with a simpler real-text method instead - never a fabricated
    occupation, and never text outside what's actually in
    occupation_data.csv/task_statements.csv.
    """
    if n <= 0 or not seed_occs or not candidates:
        return []

    seed_text = " ".join(t["text"] for occ in seed_occs for t in occ.get("sample_tasks", []))
    if not seed_text.strip():
        return []

    cand_texts = [" ".join(t["text"] for t in occ.get("sample_tasks", [])) for occ in candidates]
    valid = [(occ, text) for occ, text in zip(candidates, cand_texts) if text.strip()]
    if not valid:
        return []

    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    vectorizer = TfidfVectorizer(stop_words="english")
    matrix = vectorizer.fit_transform([seed_text] + [text for _, text in valid])
    sims = cosine_similarity(matrix[0:1], matrix[1:])[0]

    ranked = sorted(zip(valid, sims), key=lambda pair: -pair[1])
    return [occ for (occ, _text), _sim in ranked[:n]]


def expand_focus_field(selected_by_pattern: dict, all_selected: list, focus_field_code: str,
                        go_deeper: bool, hidden_ids: frozenset) -> tuple:
    """
    A real "focus on this field" preference: pull additional REAL
    occupations into whichever pattern currently has a field matching
    focus_field_code - same real SOC group first, nearest real
    task-text similarity as a fallback once that group is exhausted.
    Never fabricates an occupation outside occupation_data.csv. If
    the field isn't actually present in this student's current tree
    at all (their real evidence doesn't currently surface it under
    any shown pattern), this is a silent no-op rather than inventing
    a new area/field to attach it to.
    """
    already_ids = {occ["id"] for occ in all_selected}
    all_occs = {
        occ["id"]: occ for occ in load_career_graph()
        if occ["id"] not in hidden_ids
    }

    cap = FOCUS_EXTRA_CAP_DEEP if go_deeper else FOCUS_EXTRA_CAP

    target_pattern = None
    for pattern, occs in selected_by_pattern.items():
        if focus_field_code in group_into_fields(occs):
            target_pattern = pattern
            break
    if target_pattern is None:
        return selected_by_pattern, all_selected

    def in_field(occ_id):
        return (minor_group(occ_id) == focus_field_code
                or major_group(occ_id) == focus_field_code
                or broad_group(occ_id) == focus_field_code)

    same_group_pool = [occ for occ_id, occ in all_occs.items() if occ_id not in already_ids and in_field(occ_id)]
    added = same_group_pool[:cap]

    if len(added) < cap:
        seed_occs = [occ for occ_id, occ in all_occs.items() if in_field(occ_id)]
        excluded = already_ids | {o["id"] for o in added}
        candidates = [occ for occ_id, occ in all_occs.items() if occ_id not in excluded]
        added += nearest_by_task_similarity(seed_occs, candidates, cap - len(added))

    for occ in added:
        selected_by_pattern[target_pattern].append(occ)
        all_selected.append(occ)

    return selected_by_pattern, all_selected


def _load_reflection_shaping(session_id: str):
    """
    Real per-user Reflection preferences (Your take notes -
    hideFields/focusField), resolved to real SOC ids/field-codes at
    save time (backend/reflection_apply.py). Read fresh on every tree
    build, keyed off the session's real owning account - so removing
    a preference (deleting its chip or its note) takes effect on the
    very next Career Graph load with no separate "undo" step, and a
    preference set from one thread still applies when this student
    opens a different thread later. Anonymous sessions (no account)
    get no shaping - there is nowhere real to persist it for them.
    """
    user_id = get_session_user_id(session_id)
    if not user_id:
        return frozenset(), frozenset(), []
    return _load_reflection_shaping_for_user(user_id)


def _load_reflection_shaping_for_user(user_id: str):
    """Same as _load_reflection_shaping, for callers (Connect Threads'
    combined mode) that already have the real user id and no single
    session to resolve it from."""
    prefs = get_active_reflection_preferences(user_id)
    hidden_ids, hidden_field_codes = set(), set()
    focus_targets = []

    for p in prefs:
        extra = p.get("extra") or {}
        if p["kind"] == "hide_field":
            if extra.get("node_type") == "career" and extra.get("soc"):
                hidden_ids.add(extra["soc"])
            elif extra.get("field_code"):
                hidden_field_codes.add(extra["field_code"])
        elif p["kind"] == "focus_field" and extra.get("field_code"):
            focus_targets.append((extra["field_code"], bool(extra.get("go_deeper"))))

    return frozenset(hidden_ids), frozenset(hidden_field_codes), focus_targets


def compute_cross_links(all_selected: list, pattern_by_occ_id: dict, high_points: dict) -> list:
    """
    Cross-links only between occupations in DIFFERENT patterns.
    Rule 1: same real broad SOC group (first 6 chars).
    Rule 3: same real first-two IH high-points, in either order.
    (Rule 2 — task-embedding cosine similarity — deferred; no
    embeddings exist yet, approved deviation.)
    Cap MAX_CROSSLINKS_PER_NODE per node, MAX_CROSSLINKS_TOTAL total,
    keeping the strongest (both rules true beats either alone).
    """
    candidates = []
    n = len(all_selected)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = all_selected[i], all_selected[j]
            if pattern_by_occ_id[a["id"]] == pattern_by_occ_id[b["id"]]:
                continue

            rule1 = broad_group(a["id"]) == broad_group(b["id"])

            pts_a = high_points.get(a["id"], [])[:2]
            pts_b = high_points.get(b["id"], [])[:2]
            rule3 = len(pts_a) == 2 and set(pts_a) == set(pts_b)

            if not (rule1 or rule3):
                continue

            reasons = []
            if rule1:
                reasons.append(f"Both are part of {field_title(broad_group(a['id']))}.")
            if rule3:
                reasons.append(f"Both show the same top two interests ({', '.join(sorted(set(pts_a)))}).")

            candidates.append({
                "a": a["id"], "b": b["id"],
                "strength": (1 if rule1 else 0) + (1 if rule3 else 0),
                "reason": " ".join(reasons),
            })

    candidates.sort(key=lambda c: -c["strength"])

    per_node_count = defaultdict(int)
    result = []
    for c in candidates:
        if len(result) >= MAX_CROSSLINKS_TOTAL:
            break
        if per_node_count[c["a"]] >= MAX_CROSSLINKS_PER_NODE or per_node_count[c["b"]] >= MAX_CROSSLINKS_PER_NODE:
            continue
        result.append(c)
        per_node_count[c["a"]] += 1
        per_node_count[c["b"]] += 1

    return result


def build_career_tree(session_id: str) -> dict:
    """
    Returns {"nodes": [...], "edges": [...]} per the API contract —
    the full deterministic structure. Labels for field/career nodes
    are the real official/full titles as an honest placeholder; Phase
    2's AI-naming layer will shorten them (and add why/tryIt text)
    without touching which nodes or edges exist.
    """
    scores = get_latest_inference_scores(session_id)
    if not scores:
        return {"nodes": [{"id": "you", "type": "hub", "label": "You"}], "edges": []}

    decisions = get_latest_trait_decisions(session_id)
    hidden_ids, hidden_field_codes, focus_targets = _load_reflection_shaping(session_id)
    evidence_text = "\n".join(m["content"] for m in get_messages(session_id, evidence_only=True) if m["role"] == "user")
    return build_career_tree_core(scores, decisions, hidden_ids, hidden_field_codes, focus_targets, evidence_text)


def build_career_tree_core(scores: dict, decisions: dict, hidden_ids: frozenset,
                            hidden_field_codes: frozenset, focus_targets: list, evidence_text="") -> dict:
    """
    The actual tree-building logic build_career_tree wraps, taking its
    real inputs directly instead of a session_id to resolve them from
    - lets Connect Threads' combined mode (backend/main.py) feed it a
    freshly-scored combined transcript and cross-session decisions/
    preferences through this exact same deterministic structure,
    rather than a second tree builder.
    """
    shown_patterns = determine_shown_patterns(scores, decisions)

    if not shown_patterns:
        return {"nodes": [{"id": "you", "type": "hub", "label": "You"}], "edges": []}

    high_points = load_interest_high_points()
    selected_by_pattern, all_selected = select_occupations(
        scores, shown_patterns, high_points, hidden_ids, hidden_field_codes, evidence_text
    )

    for focus_field_code, go_deeper in focus_targets:
        selected_by_pattern, all_selected = expand_focus_field(
            selected_by_pattern, all_selected, focus_field_code, go_deeper, hidden_ids
        )

    # A pattern can have real Inference-score evidence yet end up
    # with zero real occupations whose own IH high-point actually
    # lands there (found in testing — a student's strongest axes
    # dominate FAISS's overall similarity ranking, so a secondary
    # pattern's honest matches can be genuinely absent, not just
    # ranked low). Showing an area node with nothing under it is a
    # dead end, not an honest reflection of "real evidence" — so a
    # pattern only becomes a shown area if real data actually backs
    # it with at least one occupation.
    shown_patterns = [p for p in shown_patterns if selected_by_pattern.get(p)]

    if not shown_patterns:
        return {"nodes": [{"id": "you", "type": "hub", "label": "You"}], "edges": []}

    pattern_by_occ_id = {
        occ["id"]: pattern
        for pattern, occs in selected_by_pattern.items()
        for occ in occs
    }

    # Cached by topic_relevance, so this repeats no work.
    topic_match_ids = set(topic_relevance(evidence_text)[1])

    nodes = [{"id": "you", "type": "hub", "label": "You"}]
    edges = []

    for pattern in shown_patterns:
        letter = AXIS_TO_LETTER[pattern]
        area_id = f"p:{letter}"
        # This pattern's best-ranked real occupations - tree_enrichment
        # keeps these if the relevance prune would otherwise leave the
        # area with nothing under it.
        anchor_ids = {occ["id"] for occ in selected_by_pattern[pattern][:MIN_PER_PATTERN]}
        nodes.append({
            "id": area_id, "type": "area", "label": AXIS_LABELS[pattern],
            "riasec": letter, "parent": "you",
        })
        edges.append({"source": "you", "target": area_id, "kind": "branch"})

        fields = group_into_fields(selected_by_pattern[pattern])
        labels = field_labels(fields)
        for field_code, occs in fields.items():
            # Scoped by pattern letter: the same real SOC group can
            # legitimately hold occupations under two different
            # patterns (e.g. a "15-2" occupation whose own top IH
            # point is organizes_systems, and another "15-2"
            # occupation whose top point is investigates_why) — an
            # unscoped "f:15-2" id would collide and one field would
            # silently shadow the other in a node-id lookup.
            field_id = f"f:{letter}-{field_code}"
            official_title = field_title(field_code)
            nodes.append({
                "id": field_id, "type": "field",
                "label": labels[field_code], "officialTitle": official_title,
                "parent": area_id,
            })
            edges.append({"source": area_id, "target": field_id, "kind": "branch"})

            for occ in occs:
                occ_node_id = f"o:{occ['id']}"
                nodes.append(career_node(occ, field_id))
                if occ["id"] in topic_match_ids:
                    # A strong match to the student's own words -
                    # tree_enrichment keeps these even if the AI
                    # "why" call fails or finds no quote.
                    nodes[-1]["topicMatch"] = True
                if occ["id"] in anchor_ids:
                    nodes[-1]["patternAnchor"] = True
                edges.append({"source": field_id, "target": occ_node_id, "kind": "branch"})

    cross_links = compute_cross_links(all_selected, pattern_by_occ_id, high_points)
    for link in cross_links:
        edges.append({
            "source": f"o:{link['a']}", "target": f"o:{link['b']}",
            "kind": "cross", "reason": link["reason"],
        })

    return {"nodes": nodes, "edges": edges}
