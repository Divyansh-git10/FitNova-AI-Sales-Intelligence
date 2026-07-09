"""Tests for versioned prompt loading/rendering (docs Phase 4 addendum #1)."""

from __future__ import annotations

import pytest

from fitnova.analysis.prompt_manager import PromptLoadError, PromptManager


def test_load_parses_version_and_body(tmp_path):
    (tmp_path / "greet.txt").write_text("VERSION: v2.3.4\n---\nHello $name!")
    pm = PromptManager(tmp_path)
    loaded = pm.load("greet")
    assert loaded.version == "v2.3.4"


def test_render_substitutes_variables(tmp_path):
    (tmp_path / "greet.txt").write_text("VERSION: v1.0.0\n---\nHello $name, today is $day.")
    pm = PromptManager(tmp_path)
    text, version = pm.render("greet", name="Asha", day="Monday")
    assert text == "Hello Asha, today is Monday."
    assert version == "v1.0.0"


def test_missing_file_raises(tmp_path):
    pm = PromptManager(tmp_path)
    with pytest.raises(PromptLoadError):
        pm.load("does_not_exist")


def test_missing_version_header_raises(tmp_path):
    (tmp_path / "bad.txt").write_text("no version here\n---\nbody")
    pm = PromptManager(tmp_path)
    with pytest.raises(PromptLoadError):
        pm.load("bad")


def test_missing_separator_raises(tmp_path):
    (tmp_path / "bad2.txt").write_text("VERSION: v1.0.0\nno separator body")
    pm = PromptManager(tmp_path)
    with pytest.raises(PromptLoadError):
        pm.load("bad2")


def test_render_missing_variable_raises(tmp_path):
    (tmp_path / "greet.txt").write_text("VERSION: v1.0.0\n---\nHello $name.")
    pm = PromptManager(tmp_path)
    with pytest.raises(PromptLoadError):
        pm.render("greet")


def test_load_is_cached_after_first_read(tmp_path):
    path = tmp_path / "greet.txt"
    path.write_text("VERSION: v1.0.0\n---\nHello $name.")
    pm = PromptManager(tmp_path)
    first = pm.load("greet")
    path.write_text("VERSION: v2.0.0\n---\nchanged")
    second = pm.load("greet")
    assert first.version == second.version == "v1.0.0"


def test_real_prompts_load_successfully(project_root):
    pm = PromptManager(project_root / "src" / "fitnova" / "analysis" / "prompts")
    for name in ["scoring_v1", "issue_detection_v1", "insight_generation_v1"]:
        loaded = pm.load(name)
        assert loaded.version == "v1.0.0"
