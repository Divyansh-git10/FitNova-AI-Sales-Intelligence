"""Typer CLI — the single-command entrypoint into every FitNova
subsystem (docs Phase 5): ingest, analyze, status, dashboard, export,
benchmark, doctor. Every command resolves its dependencies through the
same `bootstrap_app()` the API and dashboard use, and every read query
goes through `fitnova.db.repository` — no command hand-rolls SQL.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from fitnova.bootstrap import bootstrap_app
from fitnova.core.constants import ProcessingStatusEnum
from fitnova.db import repository
from fitnova.ingestion.folder_source import FolderSourceAdapter
from fitnova.pipeline.analysis_orchestrator import AnalysisOrchestrator
from fitnova.pipeline.orchestrator import SpeechPipelineOrchestrator

app = typer.Typer(
    name="fitnova",
    help="FitNova Sales Call Intelligence — ingest, analyze, and monitor sales calls end to end.",
    no_args_is_help=True,
)
console = Console()


# --------------------------------------------------------------------------
# fitnova ingest
# --------------------------------------------------------------------------


@app.command()
def ingest(
    watch: bool = typer.Option(
        False, "--watch", help="Keep re-scanning the inbox instead of running once."
    ),
    interval: int = typer.Option(
        30, "--interval", help="Seconds between scans when --watch is set."
    ),
) -> None:
    """Run the speech pipeline: transcribe, diarize, classify, and
    benchmark every new recording in the audio inbox."""
    container = bootstrap_app()
    settings = container.settings()
    adapter = FolderSourceAdapter(
        inbox_dir=settings.resolved_audio_inbox_dir(),
        processed_dir=settings.resolved_processed_audio_dir(),
    )
    orchestrator = SpeechPipelineOrchestrator(
        settings=settings, session_factory=container.session_factory(), adapters=[adapter]
    )

    def _run_once() -> int:
        results = orchestrator.run_once()
        if not results:
            console.print("[dim]No new recordings found.[/dim]")
            return 0
        table = Table(title="Ingest results")
        table.add_column("Call ID")
        table.add_column("Outcome")
        table.add_column("Call Type")
        for r in results:
            style = (
                "green"
                if r.outcome == "completed"
                else ("red" if r.outcome == "failed" else "yellow")
            )
            table.add_row(str(r.call_id), f"[{style}]{r.outcome}[/{style}]", r.call_type or "—")
        console.print(table)
        return len(results)

    if not watch:
        _run_once()
        return

    console.print(
        f"Watching [bold]{settings.resolved_audio_inbox_dir()}[/bold] every {interval}s. "
        "Ctrl+C to stop."
    )
    try:
        while True:
            _run_once()
            time.sleep(interval)
    except KeyboardInterrupt:
        console.print("[dim]Stopped.[/dim]")


# --------------------------------------------------------------------------
# fitnova analyze
# --------------------------------------------------------------------------


@app.command()
def analyze(
    limit: int = typer.Option(50, "--limit", help="Max calls to analyze in this batch."),
) -> None:
    """Run the AI analysis engine: score, tag issues, and generate
    coaching insight for every transcribed SALES call not yet scored."""
    container = bootstrap_app()
    settings = container.settings()
    orchestrator = AnalysisOrchestrator(
        settings=settings, session_factory=container.session_factory()
    )
    results = orchestrator.run_batch(limit=limit)

    if not results:
        console.print("[dim]No calls pending analysis.[/dim]")
        return

    table = Table(title="Analysis results")
    table.add_column("Call ID")
    table.add_column("Outcome")
    table.add_column("Overall Quality")
    table.add_column("Validated Issues")
    for r in results:
        style = (
            "green" if r.outcome == "completed" else ("red" if r.outcome == "failed" else "yellow")
        )
        table.add_row(
            str(r.call_id),
            f"[{style}]{r.outcome}[/{style}]",
            f"{r.overall_quality:.1f}" if r.overall_quality is not None else "—",
            str(r.validated_issue_count) if r.validated_issue_count is not None else "—",
        )
    console.print(table)

    outcomes: dict[str, int] = {}
    for r in results:
        outcomes[r.outcome] = outcomes.get(r.outcome, 0) + 1
    console.print(f"[bold]Summary:[/bold] {outcomes}")


# --------------------------------------------------------------------------
# fitnova status
# --------------------------------------------------------------------------


@app.command()
def status(
    limit: int = typer.Option(50, "--limit", help="Max queue rows to show."),
) -> None:
    """Show the processing queue: every call's current pipeline stage,
    status, and retry count."""
    container = bootstrap_app()
    session = container.session_factory()()
    try:
        rows = repository.queue_snapshot(session, limit=limit)
        if not rows:
            console.print("[dim]Queue is empty — nothing has been ingested yet.[/dim]")
            return

        table = Table(title=f"Processing queue (showing {len(rows)})")
        table.add_column("Call ID")
        table.add_column("Advisor")
        table.add_column("Call Type")
        table.add_column("Stage")
        table.add_column("Status")
        table.add_column("Retries")
        table.add_column("Last Error")
        status_style = {
            ProcessingStatusEnum.COMPLETED.value: "green",
            ProcessingStatusEnum.FAILED.value: "red",
            ProcessingStatusEnum.IN_PROGRESS.value: "yellow",
            ProcessingStatusEnum.PENDING.value: "dim",
        }
        for row in rows:
            style = status_style.get(row.status, "white")
            table.add_row(
                str(row.call_id),
                row.advisor_name or "—",
                row.call_type,
                row.pipeline_stage,
                f"[{style}]{row.status}[/{style}]",
                str(row.retry_count),
                (
                    (row.last_error[:60] + "…")
                    if row.last_error and len(row.last_error) > 60
                    else (row.last_error or "")
                ),
            )
        console.print(table)
    finally:
        session.close()


# --------------------------------------------------------------------------
# fitnova dashboard
# --------------------------------------------------------------------------


@app.command()
def dashboard(
    port: int = typer.Option(8501, "--port", help="Port to serve the Streamlit dashboard on."),
) -> None:
    """Launch the Streamlit dashboard."""
    home = Path(__file__).resolve().parents[3] / "dashboard" / "Home.py"
    if not home.exists():
        console.print(f"[red]Dashboard entrypoint not found at {home}[/red]")
        raise typer.Exit(code=1)
    console.print(f"Launching dashboard from {home} on port {port}...")
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(home), "--server.port", str(port)],
        check=False,
    )


# --------------------------------------------------------------------------
# fitnova export
# --------------------------------------------------------------------------


@app.command()
def export(
    kind: str = typer.Argument(
        ..., help="What to export: calls-csv | issues-csv | call-pdf | scorecard-pdf"
    ),
    output: Path = typer.Option(..., "--output", "-o", help="Output file path."),
    advisor_id: int | None = typer.Option(
        None,
        "--advisor-id",
        help="Filter by advisor (calls-csv/issues-csv) or target (scorecard-pdf).",
    ),
    team_id: int | None = typer.Option(
        None, "--team-id", help="Filter by team (calls-csv/issues-csv)."
    ),
    call_id: int | None = typer.Option(None, "--call-id", help="Target call (call-pdf)."),
) -> None:
    """Export calls/issues to CSV, or a call/scorecard report to PDF."""
    container = bootstrap_app()
    session = container.session_factory()()
    try:
        if kind == "calls-csv":
            from fitnova.reporting import calls_to_csv
            from fitnova.schemas.api_views import CallListItem

            filters = repository.CallListFilters(advisor_id=advisor_id, team_id=team_id)
            calls, _total = repository.list_calls(session, filters, page=1, page_size=10_000)
            rows = [
                CallListItem(
                    id=c.id,
                    advisor_id=c.advisor_id,
                    advisor_name=c.advisor.name if c.advisor else None,
                    team_name=c.advisor.team.name if c.advisor and c.advisor.team else None,
                    call_type=c.call_type,
                    call_datetime=c.call_datetime,
                    duration_seconds=c.duration_seconds,
                    overall_quality=c.score.overall_quality if c.score else None,
                    validated_issue_count=sum(1 for i in c.issues if i.is_validated),
                ).model_dump()
                for c in calls
            ]
            output.write_text(calls_to_csv(rows), encoding="utf-8")
            console.print(f"[green]Wrote {len(rows)} call(s) to {output}[/green]")

        elif kind == "issues-csv":
            from fitnova.reporting import issues_to_csv
            from fitnova.schemas.api_views import IssueView

            filters = repository.IssueListFilters(advisor_id=advisor_id, team_id=team_id)
            issues, _total = repository.list_issues(session, filters, page=1, page_size=10_000)
            rows = []
            for issue in issues:
                row = IssueView.model_validate(issue).model_dump()
                row["advisor_name"] = (
                    issue.call.advisor.name if issue.call and issue.call.advisor else None
                )
                rows.append(row)
            output.write_text(issues_to_csv(rows), encoding="utf-8")
            console.print(f"[green]Wrote {len(rows)} issue(s) to {output}[/green]")

        elif kind == "call-pdf":
            if call_id is None:
                console.print("[red]--call-id is required for call-pdf[/red]")
                raise typer.Exit(code=1)
            from fitnova.reporting import call_report_to_pdf

            call = repository.get_call_detail(session, call_id)
            if call is None:
                console.print(f"[red]Call {call_id} not found[/red]")
                raise typer.Exit(code=1)
            call_dict = {
                "id": call.id,
                "advisor_name": call.advisor.name if call.advisor else None,
                "team_name": call.advisor.team.name if call.advisor and call.advisor.team else None,
                "call_type": call.call_type.value,
                "call_datetime": call.call_datetime,
                "duration_seconds": call.duration_seconds,
            }
            score_dict = None
            if call.score:
                score_dict = {
                    d: getattr(call.score, d)
                    for d in (
                        "needs_discovery",
                        "rapport",
                        "empathy",
                        "listening",
                        "product_knowledge",
                        "objection_handling",
                        "compliance",
                        "trial_booking",
                        "closing",
                    )
                }
                score_dict["overall_quality"] = call.score.overall_quality
                score_dict["evidence"] = call.score.evidence
            issue_dicts = [
                {
                    "severity": i.severity.value,
                    "issue_type": i.issue_type.value,
                    "speaker": i.speaker.value,
                    "quoted_text": i.quoted_text,
                    "reason": i.reason,
                    "is_validated": i.is_validated,
                }
                for i in call.issues
            ]
            insight_dict = None
            if call.call_insight:
                insight_dict = {
                    "executive_summary": call.call_insight.executive_summary,
                    "customer_intent": call.call_insight.customer_intent,
                    "improvement_suggestions": call.call_insight.improvement_suggestions,
                    "recommended_coaching": call.call_insight.recommended_coaching,
                    "next_best_action": call.call_insight.next_best_action,
                }
            output.write_bytes(call_report_to_pdf(call_dict, score_dict, issue_dicts, insight_dict))
            console.print(f"[green]Wrote call report to {output}[/green]")

        elif kind == "scorecard-pdf":
            if advisor_id is None:
                console.print("[red]--advisor-id is required for scorecard-pdf[/red]")
                raise typer.Exit(code=1)
            from fitnova.reporting import advisor_scorecard_to_pdf

            card = repository.advisor_scorecard(session, advisor_id)
            if card is None:
                console.print(f"[red]Advisor {advisor_id} not found[/red]")
                raise typer.Exit(code=1)
            output.write_bytes(
                advisor_scorecard_to_pdf(
                    {
                        "advisor_name": card.advisor_name,
                        "team_name": card.team_name,
                        "scored_call_count": card.scored_call_count,
                        "avg_overall_quality": card.avg_overall_quality,
                        "avg_dimension_scores": card.avg_dimension_scores,
                        "issue_count_by_severity": card.issue_count_by_severity,
                        "validated_issue_count": card.validated_issue_count,
                        "total_issue_count": card.total_issue_count,
                    }
                )
            )
            console.print(f"[green]Wrote scorecard to {output}[/green]")

        else:
            console.print(
                f"[red]Unknown export kind: {kind!r}. Expected "
                "calls-csv|issues-csv|call-pdf|scorecard-pdf.[/red]"
            )
            raise typer.Exit(code=1)
    finally:
        session.close()


# --------------------------------------------------------------------------
# fitnova benchmark
# --------------------------------------------------------------------------


@app.command()
def benchmark(
    recent: int = typer.Option(10, "--recent", help="How many recent runs to list."),
) -> None:
    """Show pipeline performance: average transcription/LLM/total time
    and Real Time Factor across processed calls."""
    container = bootstrap_app()
    session = container.session_factory()()
    try:
        summary = repository.benchmark_summary(session, recent_limit=recent)
        if summary.run_count == 0:
            console.print("[dim]No pipeline runs have been benchmarked yet.[/dim]")
            return

        console.print(f"[bold]{summary.run_count}[/bold] pipeline run(s) benchmarked")
        agg_table = Table(title="Averages")
        agg_table.add_column("Metric")
        agg_table.add_column("Value")
        agg_table.add_row(
            "Total pipeline time",
            (
                f"{summary.avg_total_pipeline_time_ms:.0f} ms"
                if summary.avg_total_pipeline_time_ms
                else "—"
            ),
        )
        agg_table.add_row(
            "Transcription time",
            (
                f"{summary.avg_transcription_time_ms:.0f} ms"
                if summary.avg_transcription_time_ms
                else "—"
            ),
        )
        agg_table.add_row(
            "LLM time", f"{summary.avg_llm_time_ms:.0f} ms" if summary.avg_llm_time_ms else "—"
        )
        agg_table.add_row(
            "Real Time Factor",
            f"{summary.avg_real_time_factor:.3f}" if summary.avg_real_time_factor else "—",
        )
        console.print(agg_table)

        recent_table = Table(title=f"Most recent {len(summary.recent)} run(s)")
        recent_table.add_column("Call ID")
        recent_table.add_column("Total (ms)")
        recent_table.add_column("Transcription (ms)")
        recent_table.add_column("LLM (ms)")
        recent_table.add_column("RTF")
        recent_table.add_column("Whisper Model")
        for b in summary.recent:
            recent_table.add_row(
                str(b.call_id),
                f"{b.total_pipeline_time_ms:.0f}",
                f"{b.transcription_time_ms:.0f}" if b.transcription_time_ms else "—",
                f"{b.llm_time_ms:.0f}" if b.llm_time_ms else "—",
                f"{b.real_time_factor:.3f}" if b.real_time_factor else "—",
                b.whisper_model_used or "—",
            )
        console.print(recent_table)
    finally:
        session.close()


# --------------------------------------------------------------------------
# fitnova doctor
# --------------------------------------------------------------------------


@app.command()
def doctor() -> None:
    """Run health checks: config validity, directories, database
    connectivity, prompt files, and Ollama reachability. Exits non-zero if
    any check fails, so it's usable in a CI/pre-flight script."""
    checks: list[tuple[str, bool, str]] = []

    try:
        container = bootstrap_app()
        settings = container.settings()
        checks.append(("Bootstrap (settings + logging + DB schema)", True, ""))
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]FATAL: bootstrap failed: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    for name, path in [
        ("Audio inbox directory", settings.resolved_audio_inbox_dir()),
        ("Processed audio directory", settings.resolved_processed_audio_dir()),
        ("Data directory", settings.resolved_data_dir()),
    ]:
        checks.append((name, path.exists(), str(path)))

    try:
        weights = settings.load_weights()
        checks.append(("weights.yaml valid", True, f"scoring_version={weights.scoring_version}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(("weights.yaml valid", False, str(exc)))

    try:
        rules = settings.load_issue_rules()
        checks.append(("issue_rules.yaml valid", True, f"{len(rules.issue_types)} issue types"))
    except Exception as exc:  # noqa: BLE001
        checks.append(("issue_rules.yaml valid", False, str(exc)))

    try:
        from fitnova.analysis.prompt_manager import PromptManager

        pm = PromptManager(settings.resolved_prompts_dir())
        for prompt_name in ("scoring_v1", "issue_detection_v1", "insight_generation_v1"):
            pm.load(prompt_name)
        checks.append(
            ("Prompt templates load", True, "scoring_v1, issue_detection_v1, insight_generation_v1")
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(("Prompt templates load", False, str(exc)))

    session = container.session_factory()()
    try:
        from sqlalchemy import text

        session.execute(text("SELECT 1"))
        checks.append(("Database connectivity", True, settings.database_url))
    except Exception as exc:  # noqa: BLE001
        checks.append(("Database connectivity", False, str(exc)))
    finally:
        session.close()

    try:
        from fitnova.analysis.ollama_client import OllamaClient

        version = OllamaClient(settings).get_model_version()
        reachable = version != "unknown"
        checks.append(
            ("Ollama reachable", reachable, f"model={settings.ollama_model} version={version}")
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(("Ollama reachable", False, str(exc)))

    try:
        import webrtcvad  # noqa: F401

        checks.append(
            ("Speech extras (webrtcvad)", True, "installed — fallback diarization available")
        )
    except ImportError:
        checks.append(
            (
                "Speech extras (webrtcvad)",
                False,
                "not installed — run `pip install -r requirements-speech.txt` before processing "
                "real audio with the default DIARIZATION_BACKEND=fallback",
            )
        )

    optional_checks = {"Ollama reachable", "Speech extras (webrtcvad)"}
    table = Table(title="fitnova doctor")
    table.add_column("Check")
    table.add_column("Result")
    table.add_column("Detail")
    all_ok = True
    for name, ok, detail in checks:
        if name not in optional_checks and not ok:
            all_ok = False
        if ok:
            symbol = "[green]OK[/green]"
        elif name in optional_checks:
            symbol = "[yellow]SKIP[/yellow]"
        else:
            symbol = "[red]FAIL[/red]"
        table.add_row(name, symbol, detail)
    console.print(table)

    if not all_ok:
        console.print(
            "\n[yellow]One or more required checks failed. Ollama being unreachable and the "
            "speech extras being absent are NOT fatal — everything else (ingestion, "
            "transcription, storage, API, dashboard) works without them; only `fitnova analyze` "
            "needs a running Ollama server, and only the default fallback diarizer on real "
            "audio needs webrtcvad.[/yellow]"
        )
        raise typer.Exit(code=1)
    console.print("\n[green]All checks passed.[/green]")


if __name__ == "__main__":
    app()
