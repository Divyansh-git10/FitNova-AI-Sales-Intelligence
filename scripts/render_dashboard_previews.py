"""Release-engineering utility: real-data-driven SVG previews of two
dashboard pages, for use where a literal browser screenshot isn't
available (see docs/screenshots/README.md for why, and for how to capture
the real thing on your own machine in about 30 seconds).

Every number in these SVGs comes from a real `fitnova.db.repository` call
against a real (freshly seeded) database — the layout approximates the
actual Streamlit page structure but is hand-drawn SVG, not a pixel-exact
render of Streamlit's own CSS. That distinction is called out explicitly
in the generated file and in docs/screenshots/README.md so nobody mistakes
this for a browser screenshot.

Usage:
    python -m scripts.render_dashboard_previews
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape as _esc

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

OUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "screenshots"

_BG = "#0e1117"
_CARD = "#1c1f26"
_BORDER = "#2d3139"
_TEXT = "#e6e6e6"
_MUTED = "#9aa0a6"
_ACCENT = "#4f8df5"


def _svg_header(width: int, height: int, title: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Helvetica, Arial, sans-serif">',
        f'<rect width="{width}" height="{height}" fill="{_BG}"/>',
        f'<text x="24" y="34" fill="{_TEXT}" font-size="20" font-weight="bold">{_esc(title)}</text>',
        f'<text x="24" y="56" fill="{_MUTED}" font-size="12">'
        "Data-driven layout render (not a literal browser screenshot) — see docs/screenshots/README.md</text>",
    ]


def render_executive_overview(summary, queue_health: dict, path: Path) -> None:
    width = 900
    height = 200 + 26 * max(len(summary.calls_by_type), 1) + 80
    svg = _svg_header(width, height, "FitNova Dashboard — Home / Executive Overview")

    cards = [
        ("Total calls", str(summary.total_calls)),
        ("Scored calls", str(summary.scored_call_count)),
        (
            "Avg overall quality",
            (
                f"{summary.avg_overall_quality:.1f}"
                if summary.avg_overall_quality is not None
                else "—"
            ),
        ),
        ("Validated issues", str(summary.validated_issue_count)),
    ]
    card_w, card_h, gap, x0, y0 = 200, 90, 20, 24, 80
    for i, (label, value) in enumerate(cards):
        x = x0 + i * (card_w + gap)
        svg.append(
            f'<rect x="{x}" y="{y0}" width="{card_w}" height="{card_h}" rx="10" fill="{_CARD}" stroke="{_BORDER}"/>'
        )
        svg.append(
            f'<text x="{x + 16}" y="{y0 + 30}" fill="{_MUTED}" font-size="12">{_esc(label)}</text>'
        )
        svg.append(
            f'<text x="{x + 16}" y="{y0 + 64}" fill="{_TEXT}" font-size="28" font-weight="bold">{_esc(value)}</text>'
        )

    # Calls by type bar row
    ty = y0 + card_h + 50
    svg.append(
        f'<text x="{x0}" y="{ty}" fill="{_TEXT}" font-size="15" font-weight="bold">Calls by type</text>'
    )
    max_count = max(summary.calls_by_type.values(), default=1)
    bar_y = ty + 20
    for call_type, count in sorted(summary.calls_by_type.items(), key=lambda kv: -kv[1]):
        bar_w = int(320 * (count / max_count)) if max_count else 0
        svg.append(
            f'<text x="{x0}" y="{bar_y + 14}" fill="{_MUTED}" font-size="12">{_esc(call_type)}</text>'
        )
        svg.append(
            f'<rect x="220" y="{bar_y}" width="{max(bar_w, 4)}" height="16" rx="3" fill="{_ACCENT}"/>'
        )
        svg.append(
            f'<text x="{220 + max(bar_w, 4) + 8}" y="{bar_y + 13}" fill="{_TEXT}" font-size="12">{_esc(str(count))}</text>'
        )
        bar_y += 26

    qy = bar_y + 30
    svg.append(
        f'<text x="{x0}" y="{qy}" fill="{_TEXT}" font-size="15" font-weight="bold">Queue health</text>'
    )
    health_line = ", ".join(f"{k}: {v}" for k, v in queue_health.items())
    svg.append(
        f'<text x="{x0}" y="{qy + 22}" fill="{_MUTED}" font-size="12">{_esc(health_line)}</text>'
    )

    svg.append("</svg>")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(svg), encoding="utf-8")
    print(f"wrote {path}")


def render_queue_table(rows, path: Path) -> None:
    width = 900
    row_h = 26
    height = 100 + row_h * (len(rows) + 1)
    svg = _svg_header(
        width, height, "FitNova Dashboard — Observability & Health / Processing Queue"
    )

    cols = [
        ("Call ID", 24),
        ("Advisor", 100),
        ("Call type", 280),
        ("Stage", 460),
        ("Status", 610),
        ("Retries", 730),
    ]
    header_y = 90
    for label, x in cols:
        svg.append(
            f'<text x="{x}" y="{header_y}" fill="{_MUTED}" font-size="12" font-weight="bold">{_esc(label)}</text>'
        )
    svg.append(
        f'<line x1="24" y1="{header_y + 8}" x2="{width - 24}" y2="{header_y + 8}" stroke="{_BORDER}"/>'
    )

    status_color = {
        "COMPLETED": "#3fb950",
        "FAILED": "#f85149",
        "IN_PROGRESS": "#d29922",
        "PENDING": _MUTED,
    }
    y = header_y + 30
    for row in rows:
        svg.append(
            f'<text x="24" y="{y}" fill="{_TEXT}" font-size="12">{_esc(str(row.call_id))}</text>'
        )
        svg.append(
            f'<text x="100" y="{y}" fill="{_TEXT}" font-size="12">{_esc(row.advisor_name or "—")}</text>'
        )
        svg.append(
            f'<text x="280" y="{y}" fill="{_TEXT}" font-size="12">{_esc(str(row.call_type))}</text>'
        )
        svg.append(
            f'<text x="460" y="{y}" fill="{_TEXT}" font-size="12">{_esc(str(row.pipeline_stage))}</text>'
        )
        color = status_color.get(row.status, _TEXT)
        svg.append(
            f'<text x="610" y="{y}" fill="{color}" font-size="12">{_esc(str(row.status))}</text>'
        )
        svg.append(
            f'<text x="730" y="{y}" fill="{_TEXT}" font-size="12">{_esc(str(row.retry_count))}</text>'
        )
        y += row_h

    svg.append("</svg>")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(svg), encoding="utf-8")
    print(f"wrote {path}")


def main() -> None:
    import os

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path / 'fitnova_preview.db'}"
        os.environ["AUDIO_INBOX_DIR"] = str(tmp_path / "inbox")
        os.environ["PROCESSED_AUDIO_DIR"] = str(tmp_path / "processed")
        os.environ["DATA_DIR"] = str(tmp_path / "data")

        from fitnova.core.config import get_settings

        get_settings.cache_clear()

        import scripts.seed_demo_data as seed_mod
        from fitnova.bootstrap import bootstrap_app
        from fitnova.db import repository as repo

        seed_mod.DEMO_AUDIO_DIR = tmp_path / "demo_samples"
        container = bootstrap_app()
        seed_mod.seed(container.session_factory(), container.settings(), force=False)

        session = container.session_factory()()
        try:
            summary = repo.executive_summary(session)
            queue_health = repo.queue_health(session)
            queue_rows = repo.queue_snapshot(session, limit=50)
        finally:
            session.close()

        render_executive_overview(summary, queue_health, OUT_DIR / "dashboard_home_preview.svg")
        render_queue_table(queue_rows, OUT_DIR / "dashboard_observability_preview.svg")


if __name__ == "__main__":
    main()
