"""Owner-scoped pointers to changing, source-backed discovery evidence."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

Range = Literal["all", "30d", "90d"]
Snapshot = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class _Reference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    range: Range
    snapshot: Snapshot


class DynamicRef(_Reference):
    kind: Literal["dynamic"]
    dynamicId: str = Field(pattern=r"^d_[0-9a-f]{64}$")


class InsightRef(_Reference):
    kind: Literal["personal_insight"]
    insightId: str = Field(pattern=r"^i_[0-9a-f]{64}$")


class DayRef(_Reference):
    kind: Literal["day"]
    outcome: Literal["energy", "mood", "sleep_quality", "stress", "focus"]
    split: Literal["office_home", "commute", "steps", "screen_time", "social_share", "sleep"]


EvidenceRef = Annotated[DynamicRef | InsightRef | DayRef, Field(discriminator="kind")]
_adapter = TypeAdapter(EvidenceRef)


def parse_ref(value: str | dict) -> DynamicRef | InsightRef | DayRef:
    return _adapter.validate_json(value) if isinstance(value, str) else _adapter.validate_python(value)


class EvidenceNotFound(ValueError):
    """The pointer does not resolve to an allowed lens/owner-owned record."""


class EvidenceNotCurrent(ValueError):
    """This previously selectable comparison no longer qualifies."""


class EvidenceChanged(ValueError):
    """The preview must be reviewed again before the owner's message is stored."""

    def __init__(self):
        super().__init__("The selected evidence changed. Review it before sending.")
