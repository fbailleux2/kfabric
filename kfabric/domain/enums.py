from enum import StrEnum


class QueryStatus(StrEnum):
    CREATED = "created"
    DISCOVERED = "discovered"
    PROCESSING = "processing"
    CONSOLIDATED = "consolidated"
    INDEX_READY = "index_ready"


class CandidateStatus(StrEnum):
    DISCOVERED = "discovered"
    COLLECTED = "collected"
    FAILED = "failed"


class DocumentDecisionStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REJECTED_WITH_SALVAGE = "rejected_with_salvage"
    MANUAL_ACCEPTED = "manual_accepted"
    MANUAL_REJECTED = "manual_rejected"


class FragmentType(StrEnum):
    DATE = "date"
    REFERENCE = "reference"
    FACT = "fact"
    NUMBER = "number"
    DEFINITION = "definition"
    SIGNAL = "signal"


class VerificationStatus(StrEnum):
    TO_CONFIRM = "to_confirm"
    PLAUSIBLE = "plausible"
    INTERESTING = "interesting"
    REDUNDANT = "redundant"
    CONFIRMED = "confirmed"
    LOW_CONFIDENCE = "low_confidence"


class CorpusStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    INDEX_PREPARED = "index_prepared"


class ToolRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class SessionStatus(StrEnum):
    INITIALIZED = "initialized"
    ACTIVE = "active"
    CLOSED = "closed"
    EXPIRED = "expired"


class UserRole(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"
