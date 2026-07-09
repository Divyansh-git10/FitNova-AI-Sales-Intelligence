# Setup Guide — Windows

Tested against Windows 10/11 with Python 3.11 and PowerShell.

## 1. Prerequisites

| Requirement | Why | How to get it |
|---|---|---|
| Python 3.11+ | The project targets 3.11 | [python.org/downloads](https://www.python.org/downloads/) — check "Add python.exe to PATH" during install |
| ffmpeg | `pydub` (audio decoding) shells out to it | `winget install ffmpeg` (or download from [ffmpeg.org](https://ffmpeg.org/download.html) and add its `bin/` folder to PATH) |
| Ollama (optional) | Only needed for `fitnova analyze` (AI scoring) | [ollama.com/download](https://ollama.com/download) |
| Git | To clone the repo | [git-scm.com](https://git-scm.com/) |

Verify prerequisites:

```powershell
python --version    # should print 3.11.x or newer
ffmpeg -version      # should print an ffmpeg version, not "not recognized"
```

## 2. Clone and create a virtual environment

```powershell
git clone <this-repo-url> fitnova
cd fitnova
python -m venv .venv
.venv\Scripts\Activate.ps1
```

If PowerShell blocks the activation script with an execution-policy error,
run this once (in an elevated PowerShell) and retry:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## 3. Install dependencies

```powershell
pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

The last command registers the `fitnova` console command (`fitnova doctor`,
`fitnova dashboard`, etc.) via this project's `pyproject.toml`
`[project.scripts]` entry — without it, `fitnova` won't be on PATH and
you'd need to run `python -m fitnova.cli.main <command>` instead.

`pyannote.audio` (the optional, higher-quality diarization backend) is
**not** installed by this command — it's heavy, needs a HuggingFace token,
and the built-in `fallback` VAD-based diarizer works without any of that.
Only install it if you specifically want pyannote:

```powershell
pip install "pyannote.audio>=3.1.1"
```

## 4. Configure

```powershell
copy .env.example .env
```

The defaults work out of the box for a local run. If you want AI scoring,
also pull the model Ollama should use (must match `.env`'s
`OLLAMA_MODEL`, default `qwen3:8b`):

```powershell
ollama pull qwen3:8b
ollama serve
```

(`ollama serve` runs in the foreground — use a second terminal for the
next steps, or run it as a background service if you've installed Ollama
as a Windows service.)

## 5. Bootstrap and verify

```powershell
python -m fitnova.bootstrap
pytest
```

`pytest` should report all tests passing. If a handful of dashboard tests
fail with an import error, re-run `pip install -r requirements.txt` — it
usually means the venv wasn't fully activated when dependencies installed.

## 6. Try it

```powershell
python -m scripts.seed_demo_data
fitnova doctor
fitnova status
fitnova dashboard
```

Open `http://localhost:8501` in your browser.

## Common issues

- **`fitnova: command not found` / `'fitnova' is not recognized`** — the
  package installs a console script when you `pip install -e .` or when
  `pip install -r requirements.txt` also installs the project itself. If
  it's still missing, run commands as `python -m fitnova.cli.main <command>`
  instead, or `pip install -e .` from the repo root.
- **`ffmpeg` not found** — `pydub` needs it on PATH; reopen your terminal
  after installing so the updated PATH takes effect.
- **Whisper model download is slow or fails** — `faster-whisper` downloads
  its model from HuggingFace on first use; this requires internet access
  and can take a few minutes for larger sizes. Set `WHISPER_MODEL_SIZE=tiny`
  in `.env` for a much smaller, faster first download while testing.
- **Long paths** — if you cloned deep inside `C:\Users\...\OneDrive\...`,
  Windows' legacy 260-character path limit can bite. Clone somewhere
  shorter (e.g. `C:\dev\fitnova`) if you hit path-related errors.
