# Setup Guide — Linux

Tested against Ubuntu 22.04 with Python 3.11/3.10 and bash. Should apply
with minor package-manager substitutions on other distros.

## 1. Prerequisites

| Requirement | Why | How to get it |
|---|---|---|
| Python 3.11+ | The project targets 3.11 | `sudo apt install python3.11 python3.11-venv` (or your distro's equivalent) |
| ffmpeg | `pydub` (audio decoding) shells out to it | `sudo apt install ffmpeg` |
| Ollama (optional) | Only needed for `fitnova analyze` (AI scoring) | `curl -fsSL https://ollama.com/install.sh \| sh` |
| Git | To clone the repo | `sudo apt install git` |

Verify prerequisites:

```bash
python3.11 --version   # or python3 --version, should be 3.11.x+
ffmpeg -version
```

## 2. Clone and create a virtual environment

```bash
git clone <this-repo-url> fitnova
cd fitnova
python3.11 -m venv .venv
source .venv/bin/activate
```

## 3. Install dependencies

```bash
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

```bash
pip install "pyannote.audio>=3.1.1"
```

## 4. Configure

```bash
cp .env.example .env
```

The defaults work out of the box for a local run. If you want AI scoring,
pull the model Ollama should use (must match `.env`'s `OLLAMA_MODEL`,
default `qwen3:8b`) and start the server:

```bash
ollama pull qwen3:8b
ollama serve &     # or: systemctl --user start ollama, if installed as a service
```

## 5. Bootstrap and verify

```bash
python -m fitnova.bootstrap
pytest
```

`pytest` should report all tests passing.

## 6. Try it

```bash
python -m scripts.seed_demo_data
fitnova doctor
fitnova status
fitnova dashboard
```

Open `http://localhost:8501` in your browser (or forward the port if
you're on a remote machine: `ssh -L 8501:localhost:8501 user@host`).

## Common issues

- **`fitnova: command not found`** — the console script is installed by
  `pip install -r requirements.txt` together with the project itself; if
  it's missing, run `pip install -e .` from the repo root, or fall back to
  `python -m fitnova.cli.main <command>`.
- **`ModuleNotFoundError` for a package that's clearly installed** — check
  you activated the venv (`source .venv/bin/activate`) in the current
  shell; a fresh terminal starts deactivated.
- **`ffmpeg: not found`** — install it via your package manager and make
  sure it's on `PATH` (`which ffmpeg` should return a path).
- **Whisper model download is slow or fails** — `faster-whisper` downloads
  its model from HuggingFace on first use; this requires internet access.
  Set `WHISPER_MODEL_SIZE=tiny` in `.env` for a much smaller, faster first
  download while testing.
- **`webrtcvad` fails to build from source** — it's a C extension; install
  build tools first (`sudo apt install build-essential python3.11-dev`)
  and retry `pip install -r requirements.txt`.
- **SQLite "disk I/O error" on a network-mounted home directory** (NFS,
  some corporate VDI setups) — point `DATABASE_URL` in `.env` at a path on
  local disk, e.g. `sqlite:////tmp/fitnova/fitnova.db`.
