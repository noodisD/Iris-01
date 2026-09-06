"""
Test suite for the logging configuration system.
Verifies that configure_logging() sets up handlers, captures stack traces,
and filters logs correctly.
"""
import logging


def test_configure_logging_creates_handlers(tmp_path):
    """
    Test: configure_logging() attaches exactly 3 handlers to the agent logger.
    """
    # Need to import here to avoid loading from disk before test
    from agent.logging_config import configure_logging

    # Reset root logger to clean state
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    agent_logger = logging.getLogger("agent")
    for handler in agent_logger.handlers[:]:
        agent_logger.removeHandler(handler)

    # Configure with test log directory
    configure_logging(log_dir=str(tmp_path))

    # Verify handlers
    agent_logger = logging.getLogger("agent")

    # Should have exactly 3 handlers: file-all, file-errors, console
    assert len(agent_logger.handlers) == 3, f"Expected 3 handlers, got {len(agent_logger.handlers)}: {agent_logger.handlers}"

    handler_types = [type(h).__name__ for h in agent_logger.handlers]
    assert handler_types.count("RotatingFileHandler") == 2, f"Expected 2 RotatingFileHandlers, got {handler_types}"
    assert handler_types.count("StreamHandler") == 1, f"Expected 1 StreamHandler, got {handler_types}"


def test_error_in_except_captures_traceback(tmp_path):
    """
    Test: ERROR log within an except block auto-captures the traceback.
    """
    from agent.logging_config import configure_logging

    # Reset and configure
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    agent_logger = logging.getLogger("agent")
    for handler in agent_logger.handlers[:]:
        agent_logger.removeHandler(handler)

    configure_logging(log_dir=str(tmp_path))

    # Get the error log file
    error_log_path = tmp_path / "iris_errors.log"

    # Log an error within an except block
    test_logger = logging.getLogger("agent.test")
    try:
        raise ValueError("Test exception")
    except ValueError:
        test_logger.error("Test error message")

    # Read the error log and verify traceback is present
    assert error_log_path.exists(), f"Error log not created at {error_log_path}"
    content = error_log_path.read_text()

    assert "Test error message" in content, f"Error message not found in log:\n{content}"
    assert "ValueError: Test exception" in content, f"Exception info not found in log:\n{content}"
    assert "Traceback" in content, f"Traceback not found in log:\n{content}"


def test_info_not_in_errors_log(tmp_path):
    """
    Test: INFO logs appear in iris.log but NOT in iris_errors.log.
    """
    from agent.logging_config import configure_logging

    # Reset and configure
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    agent_logger = logging.getLogger("agent")
    for handler in agent_logger.handlers[:]:
        agent_logger.removeHandler(handler)

    configure_logging(log_dir=str(tmp_path))

    # Get log file paths
    all_log_path = tmp_path / "iris.log"
    error_log_path = tmp_path / "iris_errors.log"

    # Log an info message
    test_logger = logging.getLogger("agent.test")
    test_logger.info("Test info message")

    # Verify info appears in all_log but not in errors_log
    assert all_log_path.exists(), f"All log not created at {all_log_path}"
    all_content = all_log_path.read_text()
    assert "Test info message" in all_content, f"Info not found in all logs:\n{all_content}"

    # errors.log might not exist yet if no errors were logged
    if error_log_path.exists():
        error_content = error_log_path.read_text()
        assert "Test info message" not in error_content, f"Info should not appear in error log:\n{error_content}"


def test_idempotent_configuration(tmp_path):
    """
    Test: Calling configure_logging() twice doesn't duplicate handlers.
    """
    from agent.logging_config import configure_logging

    # Reset
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    agent_logger = logging.getLogger("agent")
    for handler in agent_logger.handlers[:]:
        agent_logger.removeHandler(handler)

    # Configure twice
    configure_logging(log_dir=str(tmp_path))
    handler_count_after_first = len(agent_logger.handlers)

    configure_logging(log_dir=str(tmp_path))
    handler_count_after_second = len(agent_logger.handlers)

    # Should be idempotent (no duplicate handlers)
    assert handler_count_after_first == handler_count_after_second, \
        f"Handler count changed from {handler_count_after_first} to {handler_count_after_second} after second configure_logging call"
    assert len(agent_logger.handlers) == 3, f"Expected 3 handlers after idempotent call, got {len(agent_logger.handlers)}"
