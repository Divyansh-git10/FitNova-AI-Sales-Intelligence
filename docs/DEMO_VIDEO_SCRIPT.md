# Demo Video Walkthrough Script

A scene-by-scene guide for recording a short (6-9 minute) walkthrough of
FitNova Sales Call Intelligence. Every command below is real — record your
terminal and browser directly running them, do not simulate any output.

Prerequisites for recording: `pip install -r requirements.txt`, `python -m
fitnova.bootstrap` run once, and ideally a local [Ollama](https://ollama.com)
server up with `.env`'s `OLLAMA_MODEL` pulled (`ollama pull qwen3:8b`) so
Scene 5 shows real scoring instead of the "not reachable" path. Both paths
are honest outcomes and worth showing — if you don't have Ollama running,
say so on camera rather than cutting away.

---

## Scene 1 — What this is (30-45s, talking head or title card)

Say, in your own words:

> "FitNova Sales Call Intelligence ingests sales call recordings,
> transcribes and diarizes them locally, scores them against a 9-dimension
> rubric, flags compliance and coaching issues with evidence-grounded
> quotes, and surfaces all of it through a REST API, a CLI, and a
> dashboard — entirely on your own machine, no data leaves it."

Show the repo root in a file explorer or `ls` briefly: `src/`, `tests/`,
`dashboard/`, `docs/`, `scripts/`.

## Scene 2 — Health check (30s)

```bash
fitnova doctor
```

Narrate: this checks config, directories, the database, prompt templates,
and whether Ollama is reachable — Ollama being down is flagged but not
fatal, since everything except `fitnova analyze` works without it.

## Scene 3 — The demo dataset (60-90s)

```bash
python -m scripts.seed_demo_data --force
```

Narrate while it runs: this seeds a small org (one company, two teams,
three advisors) and eight calls that exercise every call type the real
classifier can produce — a well-run sales call, a call with real
compliance red flags (over-promising, an undisclosed fee, pressure
tactics), a call with weak closing, a wrong number, an internal team
sync, an unsupported-language call, a call with an unresolved advisor,
and a silent recording. Mention on camera: the audio backing these is
synthetic placeholder tone (there's no offline text-to-speech available
to generate real voice audio), but the transcript text, classification,
PII redaction, and metrics are all produced by the same real code the
production pipeline uses — see the script's docstring for the full
rationale.

## Scene 4 — Full guided run (90-120s)

```bash
python -m scripts.demo
```

Let this run on camera start to finish. It narrates itself stage by
stage: bootstrap, seed, a real ingestion pipeline run on one freshly
dropped file (showing genuine Whisper transcription + diarization +
redaction + classification, or an honest "couldn't reach the model
download" message if this machine has no internet access at that
moment), an analysis attempt, and a real executive summary pulled
straight from the repository layer.

## Scene 5 — Scoring a call for real (60-90s, only if Ollama is running)

```bash
fitnova analyze
```

Narrate: this is the LLM stage — scoring against the 9-dimension rubric,
detecting issues, validating every flagged issue against the actual
transcript quote (nothing gets flagged without a real quote backing it),
and generating a coaching insight. If Ollama isn't running, run `fitnova
doctor` again to show the honest "Ollama not reachable" result instead —
do not skip this scene, showing the failure mode gracefully handled is
itself part of the demo.

## Scene 6 — The dashboard (2-3 minutes, the main event)

```bash
fitnova dashboard
```

Open `http://localhost:8501` and walk through, in order:

1. **Home** — role selector (Sales Director / Team Leader / Advisor),
   org-wide KPIs, queue health.
2. **Executive Analytics** — score distribution, issue breakdown by
   severity/type, calls-by-type.
3. **Advisor Analytics** — pick an advisor, show their scorecard and
   9-dimension breakdown.
4. **Issue Drilldown** — open a flagged issue (ideally from the
   compliance-risk demo call), show the evidence card with the actual
   quoted transcript segment it's grounded in.
5. **Transcript / call replay** — open a call, scroll the transcript,
   point out the redacted PII (`[REDACTED_PHONE]`, `[REDACTED_EMAIL]`)
   and the speaker-turn timeline.
6. **Observability & Health** — pipeline benchmarks (Real Time Factor),
   LLM stage latency/retry stats, processing queue.

Narrate as you click: every number here comes from `fitnova.db.repository`
— the same functions the API and CLI call, so the dashboard, `fitnova
status`, and `GET /calls` can never disagree.

## Scene 7 — The API (30-45s)

```bash
uvicorn fitnova.api.main:app --reload --port 8000
```

Open `http://localhost:8000/docs`, show the interactive Swagger UI, expand
one or two endpoints (`GET /analytics/executive`, `GET /issues`).

## Scene 8 — Export (20-30s)

```bash
fitnova export scorecard-pdf --advisor-id 1 --output scorecard.pdf
```

Open the generated PDF briefly.

## Scene 9 — Wrap-up (20-30s, talking head)

> "That's the full pipeline — ingestion through scoring through the
> dashboard, running locally end to end. The README covers setup on
> Windows and Linux, and `docs/FINAL_PROJECT_REPORT.md` covers the design
> decisions, trade-offs, and what I'd build next."

---

### Recording notes

- Record terminal scenes at a readable font size (18pt+); a screen
  recording tool with a visible cursor helps viewers follow along.
- It's fine — encouraged, even — to show a failure mode (Ollama down,
  Whisper needing to download its model on first run) rather than editing
  around it. The system's honest handling of those cases is a feature,
  not a blemish to hide.
- Total runtime target: 6-9 minutes. If Ollama isn't available for
  recording, Scenes 1-4 and 6-9 alone still tell the full story in about
  5-6 minutes.
