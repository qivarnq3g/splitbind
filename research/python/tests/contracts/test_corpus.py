import hashlib
import json
import struct
import subprocess
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
MANIFEST_PATH = ROOT / "fixtures" / "corpus" / "corpus-manifest.v1.json"
GENERATOR_PATH = ROOT / "research" / "python" / "scripts" / "generate_corpus.py"


def load_manifest(path: Path = MANIFEST_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generated_path(base: Path, entry: dict) -> Path:
    return base / entry["relative_path"]


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert data[12:16] == b"IHDR"
    return struct.unpack(">II", data[16:24])


def pdf_page_count(path: Path) -> int:
    return path.read_bytes().count(b"/Type /Page ")


def run_generator(output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(GENERATOR_PATH),
            "--seed",
            "20260827",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_corpus_contains_clean_and_negative_documents():
    corpus = load_manifest()
    kinds = {entry["kind"] for entry in corpus["entries"]}
    assert {"clean_pdf", "clean_image", "negative_external", "tamper_ground_truth"} <= kinds


def test_corpus_has_required_pdf_and_independent_negative_counts():
    corpus = load_manifest()
    counts = Counter(entry["kind"] for entry in corpus["entries"])
    pdf_pages = [entry["pages"] for entry in corpus["entries"] if entry["kind"] == "clean_pdf"]
    negative_seeds = {
        entry["generator_seed"]
        for entry in corpus["entries"]
        if entry["kind"] == "negative_external"
    }
    assert sum(pages == 1 for pages in pdf_pages) >= 3
    assert sum(pages > 1 for pages in pdf_pages) >= 2
    assert counts["negative_external"] >= 10
    assert len(negative_seeds) == counts["negative_external"]


def test_manifest_metadata_and_generated_artifacts_agree():
    corpus = load_manifest()
    assert corpus["schema_version"] == 1
    assert corpus["generator"] == {
        "name": "splitbind-synthetic-corpus",
        "version": "1.0.0",
        "seed": 20260827,
    }
    assert corpus["license"] == "CC0-1.0"
    assert corpus["max_fixture_bytes"] == 2_000_000

    fixture_ids = [entry["fixture_id"] for entry in corpus["entries"]]
    assert len(fixture_ids) == len(set(fixture_ids))
    for entry in corpus["entries"]:
        assert entry["generator_version"] == "1.0.0"
        assert isinstance(entry["generator_seed"], int)
        assert entry["license"] == "CC0-1.0"
        assert set(entry["dimensions"]) == {"width", "height", "unit"}
        assert entry["dimensions"]["width"] > 0
        assert entry["dimensions"]["height"] > 0
        assert entry["pages"] >= 1

        path = generated_path(ROOT / "fixtures" / "corpus", entry)
        assert path.is_file(), entry["fixture_id"]
        assert path.stat().st_size <= corpus["max_fixture_bytes"]
        assert sha256(path) == entry["sha256"]


def test_manifest_page_counts_and_dimensions_match_binary_artifacts():
    corpus = load_manifest()
    for entry in corpus["entries"]:
        path = generated_path(ROOT / "fixtures" / "corpus", entry)
        dimensions = entry["dimensions"]
        if path.suffix == ".pdf":
            assert dimensions == {"width": 612, "height": 792, "unit": "points"}
            assert pdf_page_count(path) == entry["pages"]
        elif path.suffix == ".png":
            assert dimensions["unit"] == "pixels"
            assert png_dimensions(path) == (dimensions["width"], dimensions["height"])
            assert entry["pages"] == 1
        else:
            raise AssertionError(f"Unexpected corpus format: {path.suffix}")


def test_generator_reproduces_tracked_manifest_and_bytes(tmp_path: Path):
    first_output = tmp_path / "first" / "generated"
    second_output = tmp_path / "second" / "generated"
    first = run_generator(first_output)
    second = run_generator(second_output)
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr

    first_manifest = load_manifest(first_output.parent / "corpus-manifest.v1.json")
    second_manifest = load_manifest(second_output.parent / "corpus-manifest.v1.json")
    assert first_manifest == second_manifest == load_manifest()

    for entry in first_manifest["entries"]:
        relative = Path(entry["relative_path"]).relative_to("generated")
        first_file = first_output / relative
        second_file = second_output / relative
        tracked_file = ROOT / "fixtures" / "corpus" / entry["relative_path"]
        assert sha256(first_file) == sha256(second_file) == sha256(tracked_file)


def test_corpus_metadata_contains_no_recipient_or_personal_identifiers():
    serialized = json.dumps(load_manifest(), sort_keys=True).lower()
    assert "recipient" not in serialized
    assert "email" not in serialized
    assert "person_name" not in serialized
