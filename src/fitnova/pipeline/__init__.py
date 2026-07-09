"""Pipeline orchestration: processing queue, benchmarking, and the Phase 3
speech-pipeline orchestrator.

- `queue_manager.py`  — explicit `ProcessingStatus` state transitions +
                         the dashboard-visible queue snapshot.
- `benchmarking.py`   — per-stage timing + Real Time Factor computation.
- `orchestrator.py`   — `SpeechPipelineOrchestrator`, the Phase 3 entrypoint
                         that drives ingestion -> ... -> classification with
                         idempotency and retry handling.
- `analysis_orchestrator.py` — `AnalysisOrchestrator`, the Phase 4 batch
                         entrypoint that extends the same queue rows with
                         ANALYZED -> SCORED -> VALIDATED -> STORED -> COMPLETED.
"""

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
