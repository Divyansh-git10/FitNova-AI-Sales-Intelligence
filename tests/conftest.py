"""Shared pytest fixtures.

Uses an in-memory SQLite engine for every test — never the real
`data/fitnova.db` — so the test suite is hermetic and fast, and can never
corrupt demo data.

`poolclass=StaticPool` (rather than the default per-thread pool) is
required, not just convenient: FastAPI's `TestClient` dispatches each
request's sync endpoint through a worker-thread pool, and SQLite's
`:memory:` database only exists on the connection that created it — a
different thread getting a different pooled connection would see an empty
(tableless) database. `StaticPool` pins the whole engine to one shared
connection regardless of which thread asks for it, which is exactly what
a single hermetic in-memory test database needs (Phase 5 addition, needed
once `test_api.py` started using `TestClient`).

Also provides synthetic WAV generation helpers (`make_tone_wav`,
`make_silence_wav`) so the Phase 3 speech-pipeline tests never depend on
network access or real recordings — everything is generated locally with
the stdlib `wave` module.
"""

from __future__ import annotations

import math
import os
import struct
import wave
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from fitnova.core.config import Settings, get_settings  # noqa: E402
from fitnova.db import models  # noqa: E402, F401 - registers all tables
from fitnova.db.base import Base  # noqa: E402


@pytest.fixture()
def settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture()
def engine() -> Generator[Engine, None, None]:
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture()
def db_session(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def project_root() -> Path:
    # tests/conftest.py -> tests -> project root
    return Path(__file__).resolve().parents[1]


@pytest.fixture()
def api_client(session_factory: sessionmaker[Session], settings: Settings):
    """A `fastapi.testclient.TestClient` wired to the same hermetic
    in-memory `session_factory` every other DB-touching test uses, via
    dependency overrides — the API under test never sees the real
    `data/fitnova.db`, and `get_settings` is overridden too so nothing
    triggers a second, real `bootstrap_app()` (which would try to init a
    real on-disk database) as a side effect of resolving settings."""
    from fastapi.testclient import TestClient

    from fitnova.api.deps import get_db
    from fitnova.api.deps import get_settings as api_get_settings
    from fitnova.api.main import create_app

    app = create_app()

    def _override_get_db() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[api_get_settings] = lambda: settings

    with TestClient(app) as client:
        yield client


def _write_wav(path: Path, samples: list[int], sample_rate: int) -> Path:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit PCM
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return path


def _tone_samples(duration_s: float, sample_rate: int, freq: float, amplitude: float) -> list[int]:
    n_samples = int(duration_s * sample_rate)
    peak = int(amplitude * 32767)
    return [int(peak * math.sin(2 * math.pi * freq * (i / sample_rate))) for i in range(n_samples)]


@pytest.fixture()
def make_tone_wav(tmp_path: Path):
    """Factory fixture: `make_tone_wav("call.wav", duration_s=5.0)` writes a
    synthetic sine-wave WAV (stand-in for "audio with signal") and returns
    its path."""

    def _make(
        name: str,
        duration_s: float = 5.0,
        sample_rate: int = 16000,
        freq: float = 220.0,
        amplitude: float = 0.5,
    ) -> Path:
        path = tmp_path / name
        samples = _tone_samples(duration_s, sample_rate, freq, amplitude)
        return _write_wav(path, samples, sample_rate)

    return _make


@pytest.fixture()
def make_silence_wav(tmp_path: Path):
    """Factory fixture: writes an all-zero-sample WAV — the SILENT edge case."""

    def _make(name: str, duration_s: float = 5.0, sample_rate: int = 16000) -> Path:
        path = tmp_path / name
        samples = [0] * int(duration_s * sample_rate)
        return _write_wav(path, samples, sample_rate)

    return _make
