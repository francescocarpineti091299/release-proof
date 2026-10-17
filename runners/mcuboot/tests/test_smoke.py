import json
import runpy
import sys
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.mark.parametrize("mode", ["success", "connection_error", "invalid_json", "validator_error"])
def test_saved_stream_is_closed_on_success_and_failure(monkeypatch, mode):
    smoke = runpy.run_path(str(Path(__file__).resolve().parents[1] / "smoke.py"))
    main = smoke["main"]
    raw = StringIO()
    health = BytesIO(b'{"status":"OK","templates":[]}')
    stream = BytesIO(
        b"not-json\n"
        if mode == "invalid_json"
        else b'{"type":"done","seq":0,"status":"SUCCEEDED"}\n'
    )
    response = OSError("connection failed") if mode == "connection_error" else stream
    urlopen = Mock(side_effect=[health, response])

    def validate(event):
        if mode == "validator_error":
            raise ValueError("validation failed")
        return []

    monkeypatch.setattr(sys, "argv", ["smoke.py", "--save", "capture.ndjson"])
    monkeypatch.setattr(smoke["urllib"].request, "urlopen", urlopen)
    monkeypatch.setitem(main.__globals__, "open", Mock(return_value=raw))
    monkeypatch.setitem(main.__globals__, "make_validator", lambda: ("test", validate))

    if mode == "success":
        assert main() == 0
    else:
        error = {
            "connection_error": OSError,
            "invalid_json": json.JSONDecodeError,
            "validator_error": ValueError,
        }[mode]
        with pytest.raises(error):
            main()
    assert raw.closed
    assert health.closed
    if mode != "connection_error":
        assert stream.closed
