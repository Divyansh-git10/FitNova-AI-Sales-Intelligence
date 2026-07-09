"""ORM model registry.

Importing this package guarantees every model class below has been
imported at least once, which is what makes `Base.metadata.create_all()`
(see `fitnova.db.init_db`) aware of all 16 tables. Anything that calls
`init_db()` must import `fitnova.db.models` first - `fitnova.db.init_db`
already does this for you.
"""

from fitnova.db.models.advisor import Advisor
from fitnova.db.models.audio_metadata import AudioMetadata
from fitnova.db.models.audit_log import AuditLog
from fitnova.db.models.call import Call
from fitnova.db.models.call_insight import CallInsight
from fitnova.db.models.call_metric import CallMetric
from fitnova.db.models.feedback import Feedback
from fitnova.db.models.issue import Issue
from fitnova.db.models.llm_inference_log import LLMInferenceLog
from fitnova.db.models.organization import Organization
from fitnova.db.models.pipeline_benchmark import PipelineBenchmark
from fitnova.db.models.processing_status import ProcessingStatus
from fitnova.db.models.score import Score
from fitnova.db.models.team import Team
from fitnova.db.models.transcript import Transcript
from fitnova.db.models.transcript_segment import TranscriptSegment

__all__ = [
    "Organization",
    "Team",
    "Advisor",
    "Call",
    "AudioMetadata",
    "Transcript",
    "TranscriptSegment",
    "Issue",
    "Score",
    "CallInsight",
    "CallMetric",
    "ProcessingStatus",
    "Feedback",
    "AuditLog",
    "LLMInferenceLog",
    "PipelineBenchmark",
]
