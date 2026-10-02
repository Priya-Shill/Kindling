"""
Local text embeddings with minishlab/potion-base-8M, a Model2Vec
static model: a sentence vector is just the mean of its tokens' own
fixed vectors, so there is no neural network to run, no API call and
no daily quota.

The model's two files are vendored in Outputs/embedding_model/ (see
Scripts/build_occupation_embeddings.py, which exports them) and read
here with only `tokenizers` + numpy. That is deliberate for the
512 MB free-tier host: measured in a fresh process, this path adds
about 8 MB, against roughly 100 MB for either the model2vec or the
fastembed library loading the same weights - and it needs no download
at startup. Output matches model2vec's own encode() (cosine 1.0,
checked by the build script).
"""
import os
import threading

import numpy as np

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(ROOT_DIR, "Outputs", "embedding_model")
TOKENIZER_PATH = os.path.join(MODEL_DIR, "tokenizer.json")
TOKEN_EMBEDDINGS_PATH = os.path.join(MODEL_DIR, "token_embeddings.npy")
MODEL_NAME = "minishlab/potion-base-8M"
UNK_TOKEN = "[UNK]"

_lock = threading.Lock()
_tokenizer = None
_token_embeddings = None
_unk_id = None


def _load():
    global _tokenizer, _token_embeddings, _unk_id
    if _tokenizer is not None:
        return
    with _lock:
        if _tokenizer is not None:
            return
        from tokenizers import Tokenizer
        tokenizer = Tokenizer.from_file(TOKENIZER_PATH)
        tokenizer.no_padding()
        tokenizer.no_truncation()
        # Memory-mapped: only the rows a text actually uses are ever
        # paged in, instead of holding the whole table in RAM.
        _token_embeddings = np.load(TOKEN_EMBEDDINGS_PATH, mmap_mode="r")
        _unk_id = tokenizer.token_to_id(UNK_TOKEN)
        _tokenizer = tokenizer


def embed(texts: list) -> np.ndarray:
    """One L2-normalized float32 row per text. A text with no known
    tokens gets a zero row (similarity 0 to everything)."""
    _load()
    dim = _token_embeddings.shape[1]
    out = np.zeros((len(texts), dim), dtype=np.float32)
    for row, text in enumerate(texts):
        ids = [i for i in _tokenizer.encode(text, add_special_tokens=False).ids if i != _unk_id]
        if not ids:
            continue
        vec = np.asarray(_token_embeddings[ids], dtype=np.float32).mean(axis=0)
        norm = np.linalg.norm(vec)
        if norm > 0:
            out[row] = vec / norm
    return out
