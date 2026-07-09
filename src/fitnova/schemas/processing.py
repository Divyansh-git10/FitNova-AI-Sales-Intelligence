from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from fitnova.core.constants import PipelineStage, ProcessingStatusEnum
from fitnova.schemas.common import ORMModel


class ProcessingStatusBase(BaseModel):
    pipeline_stage: PipelineStage = PipelineStage.INGESTED
    status: ProcessingStatusEnum = ProcessingStatusEnum.PENDING
    retry_count: int = 0
    last_error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ProcessingStatusCreate(ProcessingStatusBase):
    call_id: int
    content_hash: str


class ProcessingStatusRead(ProcessingStatusBase, ORMModel):
    id: int
    call_id: int
    content_hash: str
