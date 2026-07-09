# scripts/

Standalone entry points that sit outside the `fitnova` package proper —
tools for populating and demonstrating the system, not part of the
production pipeline itself.

- **`generate_demo_audio.py`** — synthesizes real, decodable placeholder
  WAV files (sine tones / silence). No offline text-to-speech engine is
  available in every environment this project might run in, so this is
  the honest stand-in: real audio bytes for the audio-validation stage to
  genuinely decode and measure, clearly documented as synthetic rather
  than passed off as real speech.

- **`seed_demo_data.py`** — populates a small demo org hierarchy and eight
  calls covering every `CallType` the real classifier can produce. Audio
  is synthetic (see above); transcript *text* is hand-authored dialogue
  standing in for what Whisper would have produced, but classification,
  PII redaction, and metrics all run through the exact same real
  functions the production pipeline uses. Never writes a `Score`, `Issue`,
  or `CallInsight` row directly — those only appear if `--analyze` is
  passed and a real local Ollama server is reachable. Idempotent by
  content hash; `--force` cleans up fully (including advisor-less
  `PENDING_METADATA` demo calls) before reseeding.

  ```bash
  python -m scripts.seed_demo_data              # seed once
  python -m scripts.seed_demo_data --force       # wipe + reseed
  python -m scripts.seed_demo_data --analyze     # also score if Ollama is up
  ```

- **`demo.py`** — the narrated, "press play" end-to-end run: bootstrap,
  seed the demo dataset, run the real speech pipeline on one freshly
  dropped file, attempt real AI analysis, and print a real executive
  summary. Used both as a manual smoke-test entry point and as the script
  behind `docs/DEMO_VIDEO_SCRIPT.md`'s recorded walkthrough.

  ```bash
  python -m scripts.demo                # full run
  python -m scripts.demo --skip-ingest   # skip the real-ingestion stage
  python -m scripts.demo --no-analyze    # skip the AI analysis stage
  ```

See each script's module docstring for the full "what's real vs. what's a
documented stand-in" breakdown — that distinction is the whole point of
how these scripts are built, not an afterthought.
