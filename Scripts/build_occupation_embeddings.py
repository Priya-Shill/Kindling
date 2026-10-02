"""
One-time (re-run only when occupation_data.csv/career_graph.json
changes) precompute of real-text local embeddings for every
occupation in Outputs/career_graph.json, so Career Graph selection
can rank topic relevance against the whole dataset without any
per-request API call at runtime.

Model: minishlab/potion-base-8M (Model2Vec static embeddings, MIT
licence) - local, no API key, no daily quota. Never Gemini: its
embedding quota (1000/day) is what this replaced.

Two steps, both safe to re-run:

  1. Export the model's runtime files to Outputs/embedding_model/
     (tokenizer.json + token_embeddings.npy as float16, ~15 MB) if
     they aren't there yet. This is the only step that needs the
     `model2vec` package and a download (`pip install model2vec`,
     dev machine only - the backend never imports it).

  2. Embed each occupation's own real title + description +
     sample_tasks text with backend/local_embedder.py - the exact
     code the backend uses for the student's words, so both sides of
     the comparison come from the same model and the same code.
     Saves after every batch and resumes from wherever a prior run
     left off, so an interruption only ever costs the current batch.

Run from the repo root:  python Scripts/build_occupation_embeddings.py
"""
import os
import sys

import numpy as np

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "Scripts"))
sys.path.insert(0, os.path.join(ROOT_DIR, "backend"))

import local_embedder
from matching import load_career_graph

OUT_PATH = os.path.join(ROOT_DIR, "Outputs", "occupation_embeddings.npz")
BATCH_SIZE = 50


def occ_text(occ: dict) -> str:
    tasks = " ".join(t["text"] for t in occ.get("sample_tasks", []))
    return f"{occ['title']}. {occ['description']} {tasks}"


def export_model_files():
    if os.path.exists(local_embedder.TOKENIZER_PATH) and os.path.exists(local_embedder.TOKEN_EMBEDDINGS_PATH):
        return
    print("exporting model files (one-time download)...")
    from model2vec import StaticModel
    model = StaticModel.from_pretrained(local_embedder.MODEL_NAME)
    os.makedirs(local_embedder.MODEL_DIR, exist_ok=True)
    model.tokenizer.save(local_embedder.TOKENIZER_PATH)
    np.save(local_embedder.TOKEN_EMBEDDINGS_PATH, model.embedding.astype(np.float16))


def check_against_model2vec(texts: list):
    """Confirms the runtime encoder reproduces the library's own
    output. Skipped when model2vec isn't installed."""
    try:
        from model2vec import StaticModel
    except ImportError:
        print("model2vec not installed - skipping the cross-check")
        return
    reference = StaticModel.from_pretrained(local_embedder.MODEL_NAME).encode(texts)
    ours = local_embedder.embed(texts)
    worst = float(np.min(np.sum(reference * ours, axis=1)))
    print(f"cross-check vs model2vec on {len(texts)} texts: lowest cosine {worst:.6f}")
    if worst < 0.999:
        raise RuntimeError("runtime encoder no longer matches model2vec's output")


def load_progress(all_ids: list):
    """Returns (done_ids_in_order, vectors) already saved, or ([], None)."""
    if not os.path.exists(OUT_PATH):
        return [], None
    data = np.load(OUT_PATH)
    # A file from a different model or encoder can't be resumed.
    if "model" not in data.files or str(data["model"]) != local_embedder.MODEL_NAME:
        return [], None
    saved_ids = list(data["ids"])
    saved_vectors = data["vectors"]
    # Only reuse the saved prefix if it's still a real prefix of the
    # current dataset order - if occupation_data.csv changed shape,
    # start over rather than risk misaligning ids with vectors.
    if saved_ids == all_ids[:len(saved_ids)]:
        return saved_ids, saved_vectors
    return [], None


def main():
    export_model_files()

    occs = load_career_graph()
    all_ids = [o["id"] for o in occs]
    all_texts = [occ_text(o) for o in occs]

    done_ids, done_vectors = load_progress(all_ids)
    start = len(done_ids)
    if start:
        print(f"resuming from {start}/{len(all_ids)} already embedded")

    if start >= len(all_ids):
        print("already complete")
        return

    vectors = [done_vectors[i] for i in range(start)] if done_vectors is not None else []

    for batch_start in range(start, len(all_ids), BATCH_SIZE):
        batch_texts = all_texts[batch_start:batch_start + BATCH_SIZE]
        vectors.extend(local_embedder.embed(batch_texts))

        # Save after every batch - a later interruption only ever
        # costs the current batch, never the whole run.
        np.savez_compressed(
            OUT_PATH,
            ids=np.array(all_ids[:len(vectors)]),
            vectors=np.array(vectors, dtype=np.float32),
            model=np.array(local_embedder.MODEL_NAME),
        )
        print(f"embedded {len(vectors)}/{len(all_ids)}")

    print(f"done: saved {len(vectors)} vectors to {OUT_PATH}")
    check_against_model2vec(all_texts[:25])


if __name__ == "__main__":
    main()
