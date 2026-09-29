"""Owner-scoped pointers to changing, source-backed discovery evidence."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

Range = Literal["all", "30d", "90d"]
Snapshot = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class _Reference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    range: Range
    snapshot: Snapshot


class PatternRef(_Reference):
    kind: Literal["pattern", "outcome_pair"]
    patternId: str = Field(min_length=1)


class CoLabelRef(_Reference):
    kind: Literal["co_label"]
    patternId: str = Field(min_length=1)
    otherId: str = Field(min_length=1)


class DayRef(_Reference):
    kind: Literal["day"]
    outcome: Literal["energy", "mood", "sleep_quality", "stress", "focus"]
    split: Literal["office_home", "commute", "steps", "screen_time", "social_share", "sleep"]


EvidenceRef = Annotated[PatternRef | CoLabelRef | DayRef, Field(discriminator="kind")]
_adapter = TypeAdapter(EvidenceRef)


def parse_ref(value: str | dict) -> PatternRef | CoLabelRef | DayRef:
    return _adapter.validate_json(value) if isinstance(value, str) else _adapter.validate_python(value)


class EvidenceNotFound(ValueError):
    """The pointer does not resolve to an allowed lens/owner-owned record."""


class EvidenceNotCurrent(ValueError):
    """This previously selectable comparison no longer qualifies."""


class EvidenceChanged(ValueError):
    """The preview must be reviewed again before the owner's message is stored."""

    def __init__(self):
        super().__init__("The selected evidence changed. Review it before sending.")
