"""Pipeline orchestration: processing queue, benchmarking, and the Phase 3
speech-pipeline orchestrator.

- `queue_manager.py`  - explicit `ProcessingStatus` state transitions +
                         the dashboard-visible queue snapshot.
- `benchmarking.py`   - per-stage timing + Real Time Factor computation.
- `orchestrator.py`   - `SpeechPipelineOrchestrator`, the Phase 3 entrypoint
                         that drives ingestion -> ... -> classification with
                         idempotency and retry handling.
- `analysis_orchestrator.py` - `AnalysisOrchestrator`, the Phase 4 batch
                         entrypoint that extends the same queue rows with
                         ANALYZED -> SCORED -> VALIDATED -> STORED -> COMPLETED.

Package-level names below are loaded lazily (PEP 562 `__getattr__`), not
imported eagerly at package-import time. `orchestrator.py` transitively
imports the diarization fallback engine, which needs `webrtcvad` - an
optional speech-extras dependency (see requirements-speech.txt) that may
not be installed. `fitnova.db.repository` imports `QueueManager` from
this package, and every API router and dashboard page imports
`fitnova.db.repository`, so an eager import here would make the entire
API/dashboard fail to start on an install that skipped the speech
extras. Lazy attribute access keeps `import fitnova.pipeline` itself
dependency-light while `fitnova.pipeline.SpeechPipelineOrchestrator`
etc. still work exactly as before, once actually accessed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fitnova.pipeline.analysis_orchestrator import AnalysisOrchestrator, AnalysisResult
    from fitnova.pipeline.benchmarking import BenchmarkRecorder
    from fitnova.pipeline.orchestrator import OrchestrationResult, SpeechPipelineOrchestrator
    from fitnova.pipeline.queue_manager import QueueManager, QueueSnapshotRow

__all__ = [
    "BenchmarkRecorder",
    "QueueManager",
    "QueueSnapshotRow",
    "SpeechPipelineOrchestrator",
    "OrchestrationResult",
    "AnalysisOrchestrator",
    "AnalysisResult",
]

_ANALYSIS_ORCHESTRATOR_NAMES = {"AnalysisOrchestrator", "AnalysisResult"}
_ORCHESTRATOR_NAMES = {"OrchestrationResult", "SpeechPipelineOrchestrator"}
_QUEUE_MANAGER_NAMES = {"QueueManager", "QueueSnapshotRow"}


def __getattr__(name: str) -> Any:
    if name == "BenchmarkRecorder":
        from fitnova.pipeline.benchmarking import BenchmarkRecorder

        return BenchmarkRecorder
    if name in _ANALYSIS_ORCHESTRATOR_NAMES:
        from fitnova.pipeline import analysis_orchestrator

        return getattr(analysis_orchestrator, name)
    if name in _ORCHESTRATOR_NAMES:
        from fitnova.pipeline import orchestrator

        return getattr(orchestrator, name)
    if name in _QUEUE_MANAGER_NAMES:
        from fitnova.pipeline import queue_manager

        return getattr(queue_manager, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
