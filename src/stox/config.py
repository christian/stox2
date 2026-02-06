from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Paths:
    root: Path
    raw: Path
    curated: Path


def get_paths() -> Paths:
    root = Path(os.environ.get("STX_DATA_ROOT", "data")).resolve()
    raw = root / "raw"
    curated = root / "curated"
    raw.mkdir(parents=True, exist_ok=True)
    curated.mkdir(parents=True, exist_ok=True)
    return Paths(root=root, raw=raw, curated=curated)
