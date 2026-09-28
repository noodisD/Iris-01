"""Observatory tracing API.

This package must not import agent.database, agent.work_queue or iris_api:
agent.database imports agent.observability.db at import time.
"""

from agent.observability.io import capture_input, capture_output
from agent.observability.tracing import (
    COMPONENTS,
    Budget,
    Component,
    apply_budget,
    close_budget,
    current_budget,
    current_traceparent,
    enabled,
    is_suppressed,
    links_from_traceparent,
    mark_error,
    open_budget,
    recording,
    set_attributes,
    setup,
    span,
    start_detached,
    suppressed,
    traced,
)

__all__ = [
    "COMPONENTS",
    "Budget",
    "Component",
    "apply_budget",
    "capture_input",
    "capture_output",
    "close_budget",
    "current_budget",
    "current_traceparent",
    "enabled",
    "is_suppressed",
    "links_from_traceparent",
    "mark_error",
    "open_budget",
    "recording",
    "set_attributes",
    "setup",
    "span",
    "start_detached",
    "suppressed",
    "traced",
]
