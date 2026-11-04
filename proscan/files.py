"""Atomic file writes: a reader never sees a half-written file."""
from contextlib import contextmanager
from pathlib import Path
import json
import os

import numpy as np


@contextmanager
def atomic(path):
    """Yield a temporary path next to `path`; it replaces `path` only on success."""
    path = Path(path)
    temporary = path.with_name('.' + path.name + '.tmp')
    try:
        yield temporary
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def save_json(path, data):
    with atomic(path) as temporary:
        temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def save_npy(path, array):
    with atomic(path) as temporary, open(temporary, 'wb') as f:
        np.save(f, array, allow_pickle=False)
