"""Chunked processing with durable checkpoints (§59.5, §60.5–§60.6).

A 500+ page document is never one in-memory object. Pages split into bounded
chunks; each chunk checkpoints to disk; failures retry the chunk only.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field

DEFAULT_CHUNK_PAGES = 10


@dataclass
class ChunkPlan:
    index: int
    pages: list[int]
    status: str = "pending"  # pending | processing | complete | failed
    attempts: int = 0
    detail: str = ""


@dataclass
class Manifest:
    job_id: str
    chunk_pages: int
    chunks: list[ChunkPlan] = field(default_factory=list)
    page_failures: dict = field(default_factory=dict)  # page_number -> error


def plan_chunks(page_numbers: list[int], chunk_pages: int = DEFAULT_CHUNK_PAGES) -> list[ChunkPlan]:
    chunk_pages = max(1, chunk_pages)
    plans = []
    for i in range(0, len(page_numbers), chunk_pages):
        plans.append(ChunkPlan(index=len(plans), pages=page_numbers[i:i + chunk_pages]))
    return plans


def work_paths(work_dir: str, job_id: str) -> tuple[str, callable]:
    root = os.path.join(work_dir, job_id)
    os.makedirs(root, exist_ok=True)

    def chunk_path(index: int) -> str:
        return os.path.join(root, f"chunk_{index:04d}.json")

    return root, chunk_path


def manifest_path(work_dir: str, job_id: str) -> str:
    root = os.path.join(work_dir, job_id)
    os.makedirs(root, exist_ok=True)
    return os.path.join(root, "manifest.json")


def load_manifest(path: str) -> Manifest | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        chunks = [ChunkPlan(**c) for c in raw.get("chunks", [])]
        return Manifest(job_id=raw.get("job_id", ""), chunk_pages=raw.get("chunk_pages", DEFAULT_CHUNK_PAGES),
                        chunks=chunks, page_failures=raw.get("page_failures", {}))
    except (OSError, ValueError, TypeError):
        return None


def save_manifest(path: str, manifest: Manifest) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({
            "job_id": manifest.job_id,
            "chunk_pages": manifest.chunk_pages,
            "chunks": [asdict(c) for c in manifest.chunks],
            "page_failures": manifest.page_failures,
        }, f)
    os.replace(tmp, path)


def save_checkpoint(path: str, payload: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, path)


def load_checkpoint(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None
