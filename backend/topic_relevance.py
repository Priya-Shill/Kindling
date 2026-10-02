"""
Generic, topic-agnostic relevance between a student's own words and
the real O*NET occupation dataset - no hand-written per-topic
keyword lists, so the same mechanism applies to any interest a
student mentions.

Two independent, free, fully-local signals:
  - semantic similarity: precomputed local embeddings
    (Outputs/occupation_embeddings.npz, built once by
    Scripts/build_occupation_embeddings.py) vs. one embedding of the
    student's own text at runtime, same model and same code on both
    sides (backend/local_embedder.py - potion-base-8M, no API call).
  - lexical relevance: BM25 over each occupation's own real
    title/description/sample_tasks text against the student's own
    words, so a literal match ("dance" vs. Dancers) is rewarded on
    top of the semantic one.

career_tree.py combines the resulting topic score with RIASEC fit
into the final hybrid ranking.
"""
import hashlib
import os
import re
import threading
from collections import OrderedDict

import numpy as np

import local_embedder
from matching import load_career_graph

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMBEDDINGS_PATH = os.path.join(ROOT_DIR, "Outputs", "occupation_embeddings.npz")

# BM25 only ever adds to an occupation the embedding already places
# in the student's neighbourhood (LEXICAL_GATE_COSINE and
# LEXICAL_GATE_Z). On its own, literal overlap is too easily
# coincidental: "watch myself in the mirror" made Watch and Clock
# Repairers the third-best BM25 hit for a dancing student, and a
# guitar student's "play"/"counter" pulled in Fast Food and Counter
# Workers. Gated, those get nothing, while a real literal match
# (Dancers, News Analysts/Reporters) is boosted further.
BM25_WEIGHT = 0.5
LEXICAL_GATE_COSINE = 0.35
LEXICAL_GATE_Z = 2.0

# z-scores are relative to this one query's own spread, so the top of
# a meaningless text ("idk", "ok cool") still looks like an outlier.
# Absolute cosine is what separates the two cases: across the
# 8-scenario test set the best real match was 0.53-0.81, while filler
# text never got above 0.28. A text whose best match is below
# TOPIC_FLOOR_COSINE carries no topic signal at all (fully trusted
# from TOPIC_FULL_COSINE up), and within a real text no single
# occupation below that floor gets positive topic credit either.
TOPIC_FLOOR_COSINE = 0.30
TOPIC_FULL_COSINE = 0.45

# An occupation that must reach the first view regardless of
# RIASEC-pattern quota (see career_tree.select_occupations): either a
# clear semantic match on its own, or a literal match backed by a
# reasonable semantic one. Capped so one very on-topic conversation
# can't fill the whole first view from a single field.
STRONG_COSINE = 0.40
STRONG_Z = 3.0
LITERAL_BM25_Z = 4.0
MAX_GUARANTEED_MATCHES = 4

# A vague conversation ("dancing" / "it just makes me happy" / "idk" /
# "not sure") averages to nothing as one text - its best cosine was
# 0.21 - even though the one message that matters is unmistakable on
# its own ("dancing" -> Dancers 0.69). So when the whole text isn't
# fully confident, each message (one per line) is scored too, and
# counts in proportion to how unsure the whole text was. A single
# short message is noisier than a conversation ("a good quote from a
# teacher" -> Substitute Teachers 0.52), so the bars are higher.
MESSAGE_FLOOR_COSINE = 0.40
MESSAGE_FULL_COSINE = 0.55
MESSAGE_STRONG_COSINE = 0.55
MESSAGE_STRONG_Z = 5.0

# A thread with fewer content words than this is no more reliable as
# a whole than a single message, so only the per-message bars apply.
MIN_WHOLE_TEXT_TOKENS = 15

EVIDENCE_CACHE_SIZE = 64

STEM_SUFFIXES = ("ingly", "edness", "ations", "ation", "ing", "edly", "ers", "ies", "er", "ed", "es", "ly", "s")

# A fixed, standard English stopword list (closed-class function
# words only - articles, pronouns, prepositions, auxiliaries) - not a
# per-topic keyword list, it applies identically to every query
# regardless of what the student is interested in. Without this,
# BM25 counts incidental overlap on "and"/"to"/"with" as if it were
# real topical signal.
_STOPWORDS = frozenset("""
a about above after again against all am an and any are aren't as at be
because been before being below between both but by can't cannot could
couldn't did didn't do does doesn't doing don't down during each few for
from further had hadn't has hasn't have haven't having he he'd he'll he's
her here here's hers herself him himself his how how's i i'd i'll i'm i've
if in into is isn't it it's its itself let's me more most mustn't my
myself no nor not of off on once only or other ought our ours ourselves
out over own same shan't she she'd she'll she's should shouldn't so some
such than that that's the their theirs them themselves then there there's
these they they'd they'll they're they've this those through to too under
until up very was wasn't we we'd we'll we're we've were weren't what
what's when when's where where's which while who who's whom why why's
with won't would wouldn't you you'd you'll you're you've your yours
yourself yourselves
""".split())


def _stem(tok: str) -> str:
    for suf in STEM_SUFFIXES:
        if len(tok) > len(suf) + 3 and tok.endswith(suf):
            return tok[:-len(suf)]
    return tok


def _tokenize(text: str) -> list:
    raw = re.findall(r"[a-zA-Z']+", text.lower())
    return [_stem(t) for t in raw if t not in _STOPWORDS]


def _occ_text(occ: dict) -> str:
    tasks = " ".join(t["text"] for t in occ.get("sample_tasks", []))
    # Title repeated so its words carry more weight in BM25's term
    # frequency - it's the occupation's own canonical identity, real
    # text, not an invented boost.
    return f"{(occ['title'] + '. ') * 4}{occ['description']} {tasks}"


class _BM25:
    """Standard BM25 (Okapi) over the fixed occupation corpus, stored
    as an inverted index of precomputed per-document weights - a few
    hundred KB of numpy arrays and a query is one small array add per
    matching term."""

    K1 = 1.5
    B = 0.75

    def __init__(self, doc_tokens: list):
        self.N = len(doc_tokens)
        doc_len = np.array([len(d) for d in doc_tokens], dtype=np.float32)
        length_norm = self.K1 * (1 - self.B + self.B * doc_len / doc_len.mean())

        postings = {}
        for doc_index, doc in enumerate(doc_tokens):
            counts = {}
            for term in doc:
                counts[term] = counts.get(term, 0) + 1
            for term, tf in counts.items():
                postings.setdefault(term, []).append((doc_index, tf))

        self.postings = {}
        for term, entries in postings.items():
            docs = np.array([d for d, _ in entries], dtype=np.int32)
            tf = np.array([t for _, t in entries], dtype=np.float32)
            idf = np.log(1 + (self.N - len(entries) + 0.5) / (len(entries) + 0.5))
            weights = idf * (tf * (self.K1 + 1)) / (tf + length_norm[docs])
            self.postings[term] = (docs, weights.astype(np.float32))

    def scores(self, query_tokens: list) -> np.ndarray:
        scores = np.zeros(self.N, dtype=np.float32)
        for term in set(query_tokens):
            entry = self.postings.get(term)
            if entry is not None:
                scores[entry[0]] += entry[1]
        return scores


_lock = threading.Lock()
_occ_ids = None
_occ_embeddings = None
_bm25 = None
_evidence_cache = OrderedDict()

NO_SIGNAL = ({}, [])


def _load_index():
    global _occ_ids, _occ_embeddings, _bm25
    if _occ_ids is not None:
        return
    with _lock:
        if _occ_ids is not None:
            return
        occs = load_career_graph()
        ids = [o["id"] for o in occs]

        data = np.load(EMBEDDINGS_PATH)
        if list(data["ids"]) != ids:
            raise RuntimeError(
                "Outputs/occupation_embeddings.npz is out of sync with "
                "career_graph.json - re-run Scripts/build_occupation_embeddings.py"
            )

        _bm25 = _BM25([_tokenize(_occ_text(o)) for o in occs])
        _occ_embeddings = data["vectors"]
        _occ_ids = ids


def _zscores(values: np.ndarray) -> np.ndarray:
    std = values.std()
    if std == 0:
        return np.zeros_like(values)
    return (values - values.mean()) / std


def _score_whole(text: str):
    """(topic score, is-strong mask, confidence) over every occupation
    for one thread's text taken as a whole."""
    cosine = _occ_embeddings @ local_embedder.embed([text])[0]
    best = float(cosine.max())
    confidence = min(1.0, max(0.0, (best - TOPIC_FLOOR_COSINE) / (TOPIC_FULL_COSINE - TOPIC_FLOOR_COSINE)))

    semantic_z = _zscores(cosine)
    lexical_z = _zscores(_bm25.scores(_tokenize(text)))
    lexical_gate = (cosine >= LEXICAL_GATE_COSINE) & (semantic_z >= LEXICAL_GATE_Z)
    lexical_boost = BM25_WEIGHT * np.maximum(lexical_z, 0) * lexical_gate

    semantic = np.where(cosine >= TOPIC_FLOOR_COSINE, semantic_z, np.minimum(semantic_z, 0))
    topic = confidence * (semantic + lexical_boost)

    strong = ((cosine >= STRONG_COSINE) & (semantic_z >= STRONG_Z)) | (
        lexical_gate & (lexical_z >= LITERAL_BM25_Z)
    )
    return topic, strong, confidence


def _score_messages(messages: list):
    """(topic score, is-strong mask) from each message on its own -
    the best any single message gives each occupation. Never negative:
    one message says nothing about what the student isn't into."""
    cosine = _occ_embeddings @ local_embedder.embed(messages).T      # (occupations, messages)
    best = cosine.max(axis=0)
    confidence = np.clip((best - MESSAGE_FLOOR_COSINE) / (MESSAGE_FULL_COSINE - MESSAGE_FLOOR_COSINE), 0.0, 1.0)

    spread = cosine.std(axis=0)
    spread[spread == 0] = 1.0
    semantic_z = (cosine - cosine.mean(axis=0)) / spread

    credit = np.where(cosine >= MESSAGE_FLOOR_COSINE, semantic_z, 0.0) * confidence
    topic = np.maximum(credit.max(axis=1), 0.0)
    strong = ((cosine >= MESSAGE_STRONG_COSINE) & (semantic_z >= MESSAGE_STRONG_Z)).any(axis=1)
    return topic, strong


def _score_segment(text: str):
    """(topic score, is-strong mask) over every occupation for one
    thread of the student's own text (one message per line), or None
    if it carries no real topic signal."""
    messages = [line.strip() for line in text.split("\n") if line.strip()]
    if len(_tokenize(text)) < MIN_WHOLE_TEXT_TOKENS:
        topic, strong = _score_messages(messages)
    else:
        topic, strong, confidence = _score_whole(text)
        if confidence < 1.0:
            message_topic, message_strong = _score_messages(messages)
            topic = np.maximum(topic, (1.0 - confidence) * message_topic)
            strong = strong | message_strong
    if not strong.any() and not (topic > 0).any():
        return None
    return topic, strong


def topic_relevance(evidence) -> tuple:
    """
    (scores, strong_ids) for the student's own words.

    scores is {occupation_id: topic score} over the whole dataset -
    roughly "standard deviations more on-topic than the average
    occupation", already scaled down to nothing for text with no real
    topic in it. strong_ids is the short, best-first list of
    occupations that must reach the first view.

    evidence is one thread's text with one message per line, or a
    list of those (Connect Threads passes one per thread) scored
    separately and combined by best score, so a dancing thread and a
    maths thread each keep their own clear matches instead of
    averaging into neither.

    Returns ({}, []) when there's no evidence, no real topic in it, or
    the local index can't be loaded - callers fall back to RIASEC-only
    ranking and never block tree building on this.
    """
    segments = [evidence] if isinstance(evidence, str) else list(evidence or [])
    segments = [s.strip() for s in segments if s and s.strip()]
    if not segments:
        return NO_SIGNAL

    key = hashlib.sha256("\x00".join(segments).encode("utf-8")).hexdigest()
    cached = _evidence_cache.get(key)
    if cached is not None:
        _evidence_cache.move_to_end(key)
        return cached

    try:
        _load_index()

        topic, strong = None, None
        for segment in segments:
            scored = _score_segment(segment)
            if scored is None:
                continue
            topic = scored[0] if topic is None else np.maximum(topic, scored[0])
            strong = scored[1] if strong is None else (strong | scored[1])

        if topic is None:
            result = NO_SIGNAL
        else:
            strong_order = [i for i in np.argsort(-topic) if strong[i]][:MAX_GUARANTEED_MATCHES]
            result = (
                {occ_id: float(t) for occ_id, t in zip(_occ_ids, topic)},
                [_occ_ids[i] for i in strong_order],
            )
    except Exception as e:
        print(f"[Topic relevance unavailable, using RIASEC-only ranking]: {e}")
        return NO_SIGNAL

    _evidence_cache[key] = result
    while len(_evidence_cache) > EVIDENCE_CACHE_SIZE:
        _evidence_cache.popitem(last=False)
    return result
