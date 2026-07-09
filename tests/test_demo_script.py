"""Smoke tests for scripts/demo.py — the narrated end-to-end walkthrough.

Runs against a real, isolated on-disk SQLite DB (same `cli_env`-style
pattern as tests/test_cli.py) rather than the hermetic in-memory
`session_factory` fixture, because `scripts.demo` calls the real
`bootstrap_app()` exactly like a user running `python -m scripts.demo`
would — this test exists to catch exactly the kind of bug a purely
unit-level test would miss (e.g. the Ollama-reachability check that
looked fine in isolation but never actually short-circuited when Ollama
was down, because `OllamaClient.get_model_version()` never raises).

Stages 3 (real ingestion) and 4 (real Ollama analysis) are exercised with
their real code paths but against a hermetic, network-unreachable Ollama
target — the point of these tests is "does the script complete and report
honestly when those subsystems are unavailable," not "is Whisper/Ollama
actually installed in CI."
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def demo_env(tmp_path, monkeypatch):
    db_path = tmp_path / "fitnova_demo_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("AUDIO_INBOX_DIR", str(tmp_path / "inbox"))
    monkeypatch.setenv("PROCESSED_AUDIO_DIR", str(tmp_path / "processed"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    # Point at a port nothing is listening on so Ollama reachability
    # resolves quickly and deterministically to "not reachable" instead of
    # depending on whatever happens to be running on localhost:11434.
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:1")

    import scripts.seed_demo_data as seed_mod

    monkeypatch.setattr(seed_mod, "DEMO_AUDIO_DIR", tmp_path / "demo_samples")

    from fitnova.core.config import get_settings

    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def test_demo_runs_end_to_end_without_ingest_or_analyze(demo_env, capsys):
    from scripts.demo import main

    sys.argv = ["demo.py", "--skip-ingest", "--no-analyze"]
    main()  # must not raise
    out = capsys.readouterr().out
    assert "Demo complete" in out
    assert "Executive summary" in out


def test_demo_analyze_stage_reports_ollama_unreachable_honestly(demo_env, capsys):
    """Regression test: stage_analyze previously always printed 'Ollama
    reachable' (get_model_version() never raises), then ran a full,
    slow, retried analysis batch that failed loudly for every call. It
    must now report "not reachable" immediately instead."""
    from scripts.demo import main

    sys.argv = ["demo.py", "--skip-ingest"]
    main()
    out = capsys.readouterr().out
    assert "Ollama not reachable" in out or "Analysis skipped" in out
    assert "Scored calls: 0" in out


def test_demo_is_rerunnable_without_reseeding_duplicates(demo_env, capsys):
    from scripts.demo import main

    sys.argv = ["demo.py", "--skip-ingest", "--no-analyze"]
    main()
    capsys.readouterr()
    main()  # second run: idempotent seed, must still complete cleanly
    out = capsys.readouterr().out
    assert "Demo complete" in out
    assert "Total calls: 8" in out  # not 16 — seeding didn't duplicate
