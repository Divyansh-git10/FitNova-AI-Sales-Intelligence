"""Release-engineering utility: capture real CLI/API output as SVG "screenshots".

Not part of the application — a one-off (or re-run-on-demand) tool that
produces docs/screenshots/*.svg for the README and final report. Every
image here is Rich's terminal-recording feature (`Console(record=True)`)
capturing the ACTUAL output of a real CLI command or a real HTTP call
against a real FastAPI app, wired to a real (freshly seeded) isolated
SQLite database — never typed-up sample output.

Dashboard pages are the one exception: this build environment has no
internet access to install a headless browser (Playwright/Chromium), so
true pixel screenshots of the Streamlit UI aren't obtainable here. See
docs/screenshots/README.md for how those are handled instead, and for how
you can capture the real thing in about 30 seconds on your own machine.

Usage:
    python -m scripts.capture_screenshots
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

OUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "screenshots"


def _setup_isolated_env(tmp_path: Path) -> None:
    import os

    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path / 'fitnova_screenshots.db'}"
    os.environ["AUDIO_INBOX_DIR"] = str(tmp_path / "inbox")
    os.environ["PROCESSED_AUDIO_DIR"] = str(tmp_path / "processed")
    os.environ["DATA_DIR"] = str(tmp_path / "data")
    os.environ["OLLAMA_BASE_URL"] = "http://localhost:1"  # deterministic "not reachable"

    from fitnova.core.config import get_settings

    get_settings.cache_clear()


def _seed(tmp_path: Path) -> None:
    import scripts.seed_demo_data as seed_mod
    from fitnova.bootstrap import bootstrap_app
    from scripts.seed_demo_data import seed

    seed_mod.DEMO_AUDIO_DIR = tmp_path / "demo_samples"
    container = bootstrap_app()
    seed(container.session_factory(), container.settings(), force=False)


def _capture_cli(name: str, call) -> None:
    """Run one CLI command function with a recording Console, export SVG."""
    from rich.console import Console

    import fitnova.cli.main as clim

    recorder = Console(record=True, width=104)
    original = clim.console
    clim.console = recorder
    try:
        try:
            call(clim)
        except SystemExit:
            pass
        except Exception as exc:  # noqa: BLE001 - typer.Exit subclasses SystemExit in some versions
            recorder.print(f"[red]{type(exc).__name__}: {exc}[/red]")
    finally:
        clim.console = original

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"cli_{name}.svg"
    recorder.save_svg(str(path), title=f"$ fitnova {name.replace('_', ' ')}")
    print(f"wrote {path}")


def capture_cli_screenshots(tmp_path: Path) -> None:

    _capture_cli("doctor", lambda m: m.doctor())
    _capture_cli("status", lambda m: m.status(limit=50))
    _capture_cli("ingest", lambda m: m.ingest(watch=False, interval=30))
    _capture_cli("analyze", lambda m: m.analyze(limit=50))
    _capture_cli("benchmark", lambda m: m.benchmark(recent=10))


def capture_api_screenshots() -> None:
    """Real HTTP calls against a real FastAPI app (in-process TestClient —
    same ASGI app `uvicorn fitnova.api.main:app` serves), rendered as a
    terminal-style request/response transcript."""
    from fastapi.testclient import TestClient
    from rich.console import Console
    from rich.panel import Panel
    from rich.syntax import Syntax

    from fitnova.api.main import create_app

    app = create_app()
    client = TestClient(app)

    calls = [
        ("GET", "/health"),
        ("GET", "/analytics/executive"),
        ("GET", "/calls?page=1&page_size=5"),
        ("GET", "/issues?page=1&page_size=5"),
        ("GET", "/observability/llm"),
    ]

    recorder = Console(record=True, width=104)
    for method, path in calls:
        response = client.request(method, path)
        recorder.print(
            f"[bold green]{method}[/bold green] [bold]{path}[/bold]  ->  "
            f"[bold]{response.status_code}[/bold]"
        )
        try:
            body = json.dumps(response.json(), indent=2)[:1200]
        except Exception:  # noqa: BLE001
            body = response.text[:1200]
        recorder.print(Panel(Syntax(body, "json", background_color="default"), border_style="dim"))
        recorder.print()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "api_walkthrough.svg"
    recorder.save_svg(str(out_path), title="FastAPI — real requests against the ASGI app")
    print(f"wrote {out_path}")


def main() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _setup_isolated_env(tmp_path)
        _seed(tmp_path)
        capture_cli_screenshots(tmp_path)
        capture_api_screenshots()


if __name__ == "__main__":
    main()
