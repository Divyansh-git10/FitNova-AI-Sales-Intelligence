"""Versioned prompt loading and rendering.

Prompts live as plain text files under `analysis/prompts/`, not inline
Python f-strings. Each file's first line is `VERSION: vX.Y.Z`, followed by
a `---` separator, followed by the template body using `$variable`
placeholders (stdlib `string.Template` syntax — deliberately NOT
`.format()`/f-strings, since prompt bodies contain literal `{`/`}`
characters in JSON schema examples that would collide with `.format()`'s
brace syntax).

`prompt_version` is what gets recorded on every `llm_inference_logs` row
(docs Section 12) — bumping a prompt's behavior means editing the file AND
changing its `VERSION` line, at which point every subsequent inference is
traceably on the new version while historical logs still show what
produced them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from string import Template

from fitnova.core.logging_config import get_logger

logger = get_logger(__name__)


class PromptLoadError(Exception):
    """Raised when a prompt file is missing or malformed (no VERSION
    header, no `---` separator)."""


@dataclass(frozen=True)
class LoadedPrompt:
    name: str
    version: str
    template: Template


class PromptManager:
    """Loads and renders versioned prompt templates from a directory."""

    def __init__(self, prompts_dir: Path) -> None:
        self.prompts_dir = Path(prompts_dir)
        self._cache: dict[str, LoadedPrompt] = {}

    def load(self, name: str) -> LoadedPrompt:
        if name in self._cache:
            return self._cache[name]

        path = self.prompts_dir / f"{name}.txt"
        if not path.exists():
            raise PromptLoadError(f"Prompt file not found: {path}")

        raw = path.read_text(encoding="utf-8")
        prompt = _parse_prompt(name, raw)
        self._cache[name] = prompt
        logger.debug("Loaded prompt '%s' version=%s from %s", name, prompt.version, path)
        return prompt

    def render(self, prompt_name: str, /, **variables: str) -> tuple[str, str]:
        """Returns `(rendered_text, prompt_version)`.

        `prompt_name` is positional-only (the `/`) so that callers can pass
        a template variable literally called `name` (or `prompt_name`)
        through `**variables` without colliding with this method's own
        parameter — `prompt_vars` in `llm_client.py` is caller-controlled
        and its keys are not restricted."""
        prompt = self.load(prompt_name)
        try:
            rendered = prompt.template.substitute(**variables)
        except KeyError as exc:
            raise PromptLoadError(
                f"Prompt '{prompt_name}' (version {prompt.version}) is missing a required "
                f"variable: {exc}"
            ) from exc
        return rendered, prompt.version


def _parse_prompt(name: str, raw: str) -> LoadedPrompt:
    if "\n---\n" not in raw:
        raise PromptLoadError(
            f"Prompt '{name}' is missing the 'VERSION: vX.Y.Z' header / '---' separator"
        )
    header, body = raw.split("\n---\n", 1)
    header = header.strip()
    if not header.startswith("VERSION:"):
        raise PromptLoadError(f"Prompt '{name}' header must start with 'VERSION:', got: {header!r}")

    version = header.split("VERSION:", 1)[1].strip()
    if not version:
        raise PromptLoadError(f"Prompt '{name}' has an empty VERSION")

    return LoadedPrompt(name=name, version=version, template=Template(body))
