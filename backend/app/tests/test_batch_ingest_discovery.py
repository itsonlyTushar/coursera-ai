"""Tests for the batch-ingest script's discovery logic (backend/scripts/batch_ingest.py):
pairing flat quiz/exam question+solution files and building the full unit list. Pure
filesystem logic — no network, no backend, no ML deps involved.
"""
import importlib.util
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "batch_ingest.py"
spec = importlib.util.spec_from_file_location("batch_ingest", SCRIPT_PATH)
batch_ingest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch_ingest)


# Asserts a question PDF and its "_SOLUTION" sibling are paired into one item.
def test_discover_quiz_pairs_matches_solution_suffix(tmp_path):
    (tmp_path / "Assignment1.pdf").touch()
    (tmp_path / "Assignment1_SOLUTION.pdf").touch()

    pairs = batch_ingest.discover_quiz_pairs(tmp_path)

    assert len(pairs) == 1
    base, question, solution = pairs[0]
    assert base == "Assignment1"
    assert question.name == "Assignment1.pdf"
    assert solution.name == "Assignment1_SOLUTION.pdf"


# Asserts a lone solution (no matching question) is still surfaced, not dropped.
def test_discover_quiz_pairs_handles_lone_solution(tmp_path):
    (tmp_path / "Quiz2_SOLUTION.pdf").touch()

    pairs = batch_ingest.discover_quiz_pairs(tmp_path)

    assert len(pairs) == 1
    base, question, solution = pairs[0]
    assert question is None
    assert solution.name == "Quiz2_SOLUTION.pdf"


# Asserts pairing is case- and separator-insensitive on the "solution" suffix.
def test_discover_quiz_pairs_case_and_separator_insensitive(tmp_path):
    (tmp_path / "Exam_1.pdf").touch()
    (tmp_path / "Exam_1_solution.pdf").touch()

    pairs = batch_ingest.discover_quiz_pairs(tmp_path)

    assert len(pairs) == 1
    assert pairs[0][0] == "Exam_1"


# Asserts a folder with no recognized per-unit files but with flat documents is expanded
# into one unit per pair, while a folder with unrelated files (docx/png) is skipped entirely.
def test_discover_units_expands_flat_container_and_skips_unrelated(tmp_path):
    course = tmp_path / "course"
    (course / "lec01").mkdir(parents=True)
    (course / "lec01" / "transcript.md").touch()

    (course / "assignments").mkdir()
    (course / "assignments" / "Assignment1.pdf").touch()
    (course / "assignments" / "Assignment1_SOLUTION.pdf").touch()

    (course / "random_stuff").mkdir()
    (course / "random_stuff" / "notes.docx").touch()

    units = batch_ingest.discover_units(course, only=None, exclude=set())
    unit_ids = {unit_id for unit_id, _ in units}

    assert "lec01" in unit_ids
    assert "assignments-assignment1" in unit_ids
    assert not any(u.startswith("random_stuff") for u in unit_ids)
    assert len(units) == 2


# Asserts --exclude removes a unit by id even though it has valid, ingestable assets.
def test_discover_units_respects_exclude(tmp_path):
    course = tmp_path / "course"
    for lecture in ("lec01", "lec02"):
        (course / lecture).mkdir(parents=True)
        (course / lecture / "transcript.md").touch()

    units = batch_ingest.discover_units(course, only=None, exclude={"lec02"})

    assert [unit_id for unit_id, _ in units] == ["lec01"]


# Asserts numbered names sort numerically (lec10 after lec2), not alphabetically.
def test_sort_key_numeric_order():
    names = ["lec10", "lec2", "lec1"]
    assert sorted(names, key=batch_ingest._sort_key) == ["lec1", "lec2", "lec10"]
