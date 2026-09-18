"""The run command explains failures instead of exiting silently."""

from inspect_ai._util.error import PrerequisiteError

import caretaker.run as run


def test_startup_error_is_printed(monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise PrerequisiteError("ERROR: the anthropic package is required")

    monkeypatch.setattr(run, "inspect_eval", fail)
    assert run.run_eval([], "anthropic/claude-fable-5-1", "logs/unused") is None
    assert "the anthropic package is required" in capsys.readouterr().out
