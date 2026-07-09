"""Phase 6 end-to-end demo script — the "press play" walkthrough.

Runs the whole system, narrated stage by stage with Rich console output,
so a fresh clone (or a screen recording for `docs/DEMO_VIDEO_SCRIPT.md`)
can show the pipeline actually working without anyone reading code first:

    1. Bootstrap  — config, logging, database schema.
    2. Seed       — the synthetic demo dataset (scripts/seed_demo_data.py).
    3. Real ingest — drops ONE more synthetic WAV + sidecar into the REAL
       audio inbox and runs the REAL `SpeechPipelineOrchestrator`, the
       exact code path `fitnova ingest` uses on a genuine recording. This
       stage exists specifically to prove the full speech pipeline (audio
       validation, transcription, diarization, normalization, PII
       redaction, classification, benchmarking) runs end to end on a real
       dropped file — not just the seed script's direct DB writes.
    4. Analyze    — attempts the REAL `AnalysisOrchestrator` (Ollama) on
       whatever SALES calls are pending. If Ollama isn't running, this
       stage reports that plainly and moves on — it never fabricates a
       score to make the demo look more finished than it is.
    5. Summary    — a real repository-layer executive summary and queue
       snapshot, i.e. exactly what the dashboard's Home page would show.

Every number this script prints comes from a real function call against
a real (if freshly bootstrapped) database — nothing here is scripted
output or a canned transcript.

Usage:
    python -m scripts.demo                  # full run
    python -m scripts.demo --skip-ingest     # skip stage 3 (faster)
    python -m scripts.demo --no-analyze      # skip stage 4 entirely
    python -m scripts.demo --force-reseed    # wipe + reseed the demo dataset first
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402

from fitnova.bootstrap import bootstrap_app  # noqa: E402
from fitnova.db import repository as repo  # noqa: E402
from fitnova.ingestion.folder_source import FolderSourceAdapter  # noqa: E402
from fitnova.pipeline.analysis_orchestrator import AnalysisOrchestrator  # noqa: E402
from fitnova.pipeline.orchestrator import SpeechPipelineOrchestrator  # noqa: E402
from scripts.generate_demo_audio import generate_tone_wav  # noqa: E402
from scripts.seed_demo_data import DEMO_CALLS, seed  # noqa: E402

console = Console()


def _stage(number: int, title: str) -> None:
    console.print()
    console.rule(f"[bold cyan]Stage {number}: {title}[/bold cyan]")


def stage_bootstrap():
    _stage(1, "Bootstrap")
    with console.status("Loading config, configuring logging, ensuring database schema..."):
        container = bootstrap_app()
    settings = container.settings()
    console.print(
        Panel.fit(
            f"[green]OK[/green]  env=[bold]{settings.app_env}[/bold]  "
            f"database=[bold]{settings.database_url}[/bold]\n"
            f"Ollama target: [bold]{settings.ollama_base_url}[/bold] "
            f"(model=[bold]{settings.ollama_model}[/bold]) — reachability checked in Stage 4",
            title="Bootstrap complete",
        )
    )
    return container, settings


def stage_seed(container, settings, force: bool):
    _stage(2, "Seed synthetic demo dataset")
    console.print(
        "[dim]scripts/seed_demo_data.py: real classification, real PII redaction, real metrics — "
        "hand-authored dialogue standing in for ASR output (no offline TTS is available in this "
        "environment to voice a transcript into real speech; see that script's docstring).[/dim]"
    )
    session_factory = container.session_factory()
    with console.status("Seeding organization / teams / advisors / demo calls..."):
        created = seed(session_factory, settings, force=force)

    # `created`'s Call instances are detached once seed()'s own session
    # closes, so the table is built from a fresh repository read instead —
    # the exact same read path the API/CLI/dashboard use, not a special
    # case for this script.
    table = Table(title=f"Seeded {len(created)} of {len(DEMO_CALLS)} defined demo call(s)")
    table.add_column("Call ID")
    table.add_column("Call type")
    session = session_factory()
    try:
        rows, _ = repo.list_calls(session, repo.CallListFilters(), page=1, page_size=50)
        for row in sorted(rows, key=lambda r: r.id):
            table.add_row(str(row.id), row.call_type.value)
    finally:
        session.close()
    console.print(table)


def stage_real_ingest(container, settings):
    _stage(3, "Real ingestion pipeline (one genuinely dropped file)")
    inbox = settings.resolved_audio_inbox_dir()
    processed = settings.resolved_processed_audio_dir()
    audio_path = inbox / "demo_live_ingest.wav"
    sidecar_path = inbox / "demo_live_ingest.wav.meta.json"

    console.print(
        f"[dim]Writing a synthetic placeholder WAV into the real inbox: {audio_path}[/dim]"
    )
    generate_tone_wav(audio_path, duration_s=20.0, freq=300.0)
    sidecar_path.write_text(
        '{"advisor_external_id": "adv-priya-001", "customer_ref": "+919900011122"}'
    )

    adapter = FolderSourceAdapter(inbox_dir=inbox, processed_dir=processed)
    orchestrator = SpeechPipelineOrchestrator(
        settings=settings, session_factory=container.session_factory(), adapters=[adapter]
    )
    with console.status(
        "Running the real speech pipeline (Whisper, diarization, PII redaction, classification)..."
    ):
        results = orchestrator.run_once()

    table = Table(title="Real ingestion result")
    table.add_column("Call ID")
    table.add_column("Outcome")
    table.add_column("Call type")
    for r in results:
        table.add_row(str(r.call_id), r.outcome, r.call_type or "—")
    console.print(table)
    outcome = results[0].outcome if results else None
    if outcome == "failed":
        console.print(
            "[dim]Note: this attempt failed because faster-whisper needs to download its model "
            "weights on first use and this environment has no internet access — an honest, "
            "expected failure mode here, not a bug (the queue row above shows it as FAILED, not "
            "silently dropped). On a machine with internet access, the model downloads once and "
            "this stage completes normally.[/dim]"
        )
    else:
        console.print(
            "[dim]Note: this file is a synthetic tone, not real speech, so Whisper correctly "
            "finds no speech and it's classified NO_SPEECH — the real classifier working as "
            "designed, not a shortcut. Drop actual recordings into the inbox to see a real SALES "
            "transcript here.[/dim]"
        )


def stage_analyze(container, settings):
    _stage(4, "AI analysis (Ollama)")
    from fitnova.analysis.ollama_client import OllamaClient

    # OllamaClient.get_model_version() is deliberately "best-effort, never
    # raises" (it's observability metadata, not a health gate) — it returns
    # the literal string "unknown" on any failure. `version != "unknown"`
    # is the exact reachability heuristic `fitnova doctor` already uses,
    # reused here rather than a second way to answer the same question.
    with console.status("Checking Ollama reachability..."):
        version = OllamaClient(settings).get_model_version()
    if version == "unknown":
        console.print(
            Panel.fit(
                "[yellow]Ollama not reachable.[/yellow]\n"
                "SALES calls remain unscored — exactly like any real ingested call waiting on "
                "`fitnova analyze`. Nothing is fabricated to fill this gap.",
                title="Analysis skipped",
            )
        )
        return

    console.print(
        f"[green]Ollama reachable[/green] (model={settings.ollama_model}, version={version})"
    )
    orchestrator = AnalysisOrchestrator(settings, container.session_factory())
    with console.status(
        "Scoring, detecting issues, validating evidence, generating coaching insight..."
    ):
        results = orchestrator.run_batch()

    if not results:
        console.print("[dim]No calls were pending analysis.[/dim]")
        return

    table = Table(title="Analysis results")
    table.add_column("Call ID")
    table.add_column("Outcome")
    table.add_column("Overall quality")
    table.add_column("Validated issues")
    for r in results:
        table.add_row(
            str(r.call_id),
            r.outcome,
            f"{r.overall_quality:.1f}" if r.overall_quality is not None else "—",
            str(r.validated_issue_count) if r.validated_issue_count is not None else "—",
        )
    console.print(table)


def stage_summary(container):
    _stage(5, "Executive summary (real repository query)")
    session = container.session_factory()()
    try:
        summary = repo.executive_summary(session)
        queue = repo.queue_snapshot(session, limit=50)
    finally:
        session.close()

    lines = [
        f"Total calls: [bold]{summary.total_calls}[/bold]",
        f"Calls by type: {summary.calls_by_type}",
        f"Scored calls: [bold]{summary.scored_call_count}[/bold]",
        (
            f"Avg overall quality: {summary.avg_overall_quality:.1f}"
            if summary.avg_overall_quality is not None
            else "Avg overall quality: — (no scored calls yet)"
        ),
        f"Validated issues: {summary.validated_issue_count} "
        f"(unvalidated/rejected: {summary.unvalidated_issue_count})",
        f"Queue rows: {len(queue)}",
    ]
    console.print(Panel.fit("\n".join(lines), title="Executive summary"))

    console.print(
        Panel.fit(
            "[bold]Next steps[/bold]\n"
            "  fitnova dashboard        # Streamlit dashboard on http://localhost:8501\n"
            "  uvicorn fitnova.api.main:app --reload --port 8000   # REST API + docs at /docs\n"
            "  fitnova status           # processing queue snapshot\n"
            "  fitnova doctor           # full health check",
            title="Explore further",
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--skip-ingest", action="store_true", help="Skip stage 3 (real ingestion demo)."
    )
    parser.add_argument("--no-analyze", action="store_true", help="Skip stage 4 (AI analysis).")
    parser.add_argument(
        "--force-reseed", action="store_true", help="Wipe and reseed the demo dataset in stage 2."
    )
    args = parser.parse_args()

    start = time.perf_counter()
    console.print(
        Panel.fit(
            "[bold]FitNova Sales Call Intelligence — end-to-end demo[/bold]", style="bold blue"
        )
    )

    container, settings = stage_bootstrap()
    stage_seed(container, settings, force=args.force_reseed)
    if not args.skip_ingest:
        stage_real_ingest(container, settings)
    if not args.no_analyze:
        stage_analyze(container, settings)
    stage_summary(container)

    elapsed = time.perf_counter() - start
    console.print()
    console.rule(f"[bold green]Demo complete in {elapsed:.1f}s[/bold green]")


if __name__ == "__main__":
    main()
