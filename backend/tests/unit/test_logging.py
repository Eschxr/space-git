import json
import logging

from scene_tracker.core.logging import JsonFormatter


def test_structured_log():
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    record.correlation_id = "request-1"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "hello world"
    assert payload["correlation_id"] == "request-1"
    assert payload["level"] == "INFO"
