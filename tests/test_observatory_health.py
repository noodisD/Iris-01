from agent.observability.health import WindowStats, evaluate


def _stats(**overrides: WindowStats) -> dict[str, WindowStats]:
    base = {name: WindowStats() for name in (
        "http", "db", "queue", "pipeline", "engine", "admission", "chat", "voice",
        "llm", "import", "sensors", "ideas", "insights", "system", "web", "android",
    )}
    base.update(overrides)
    return base


def _state(component: str, **kwargs: object) -> str:
    stats = kwargs.pop("stats", _stats())
    probe = kwargs.pop("probe", {"stale": False, "queue": {}, "db": {"reachable": True}, "pool": {}, "worker": {"alive": True}, "loop": {}, "process": {}, "observatory": {}})
    client_state = kwargs.pop("client_state", {})
    found = {item.id: item for item in evaluate(stats, probe, client_state)}
    return found[component].state


def test_exhausted_queue_is_failing_and_a_backlog_is_degraded():
    probe = {"stale": False, "queue": {"exhausted": 1, "due": 0}, "worker": {"alive": True}, "db": {"reachable": True}, "pool": {}, "loop": {}, "process": {}, "observatory": {}}
    assert _state("queue", probe=probe) == "failing"
    probe["queue"] = {"exhausted": 0, "due": 11, "scheduled_retry": 0}
    assert _state("queue", probe=probe) == "degraded"


def test_unreachable_database_fails_and_a_busy_pool_degrades():
    probe = {"stale": False, "db": {"reachable": False, "error": "down"}, "pool": {"in_use": 0, "max": 20}, "queue": {}, "worker": {"alive": True}, "loop": {}, "process": {}, "observatory": {}}
    assert _state("db", probe=probe) == "failing"
    probe["db"] = {"reachable": True}
    probe["pool"] = {"in_use": 15, "max": 20}
    assert _state("db", probe=probe) == "degraded"


def test_six_requests_with_two_server_errors_fail_http():
    stats = _stats(http=WindowStats(calls=6, server_errors=2))
    assert _state("http", stats=stats, probe={"stale": False, "listeners": {}}) == "failing"


def test_a_quarter_second_stall_degrades_the_process():
    probe = {"stale": False, "loop": {"lag_ms_max": 250, "threadpool_busy": 0}, "process": {"rss_bytes": 1}, "observatory": {"dropped": 0, "write_failures": 0, "history": []}}
    assert _state("system", probe=probe) == "degraded"


def test_three_unreachable_attempts_fail_android():
    assert _state("android", client_state={"android": {"state": {"collector": {"unreachable_streak": 3}}}}) == "failing"


def test_feature_components_are_idle_without_activity():
    health = {item.id: item.state for item in evaluate(_stats(), None, {})}
    for name in ("chat", "voice", "import", "sensors", "ideas", "insights"):
        assert health[name] == "idle"
