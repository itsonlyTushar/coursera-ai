"""Generic resumable JSONL checkpoint I/O for long-running API-driven batch jobs.

Single source of truth for what used to be two structurally identical
load/append pairs in visual_analysis.py and embeddings.py.
"""
import json
from pathlib import Path


def load_jsonl_checkpoint(checkpoint_path: Path) -> list[dict]:
    """Load previously completed records from a JSONL checkpoint file."""

    if not checkpoint_path.exists():
        return []

    records = []

    with open(checkpoint_path, "r", encoding='utf-8') as checkpoint_file:

        for line_number, line in enumerate(checkpoint_file, start=1):

            line = line.strip()

            if not line:
                continue

            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"skipping invalid checkpoint line {line_number}: {line}")

    return records


def append_jsonl_checkpoint(checkpoint_path: Path, record: dict) -> None:
    """Append one completed record to a JSONL checkpoint file, saving progress immediately."""

    with open(checkpoint_path, "a", encoding='utf-8') as file:
        file.write(json.dumps(record, ensure_ascii=False) + '\n')
