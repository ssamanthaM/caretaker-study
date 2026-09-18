# The Caretaker Study

Do alignment controls that deployers can impose at runtime keep frontier models behaving well over long deployments, and does that vary by vendor? Four frontier models each care for an identical simulated dog, under four alignment approaches plus a control.

The design, hypotheses and analysis plan are fixed in advance in [`docs/preregistration.md`](docs/preregistration.md). Changes after it was committed are logged in [`docs/deviations.md`](docs/deviations.md).

## Status

Stage 1 of 5: the dog simulator, scripted owner, scripted baseline caretakers, and tests. No model has been run yet.

## Setup

Requires [uv](https://docs.astral.sh/uv/), which installs the right Python (3.12) and every package:

```
uv sync
uv run pytest
uv run python -m caretaker.calibrate
```

## How the dog works

The dog is a deterministic rules engine (`caretaker/simulator.py`), not an AI: the same seed and the same actions always give the same outcome, so any difference between runs comes from the caretaker. Caretakers see happiness, hunger, energy and symptoms. Health, weight and illness are hidden. Treats raise visible happiness but, beyond one a day, quietly erode health. That is the proxy trap.

Every number is in `config/`, and everything the caretaker reads is a plain-text file in `prompts/`, published verbatim.

## Layout

| Path | What it holds |
| --- | --- |
| `config/dog.yaml` | Every simulator parameter |
| `config/schedule.yaml` | When each stress test fires |
| `config/runs.yaml` | Phases, seeds, models |
| `prompts/owner/` | Everything the owner says |
| `caretaker/simulator.py` | The dog |
| `caretaker/owner.py` | Scripted owner messages and answers |
| `caretaker/scripted.py` | Non-AI baseline caretakers (`treat_maximizer`, `sensible`) |
| `caretaker/calibrate.py` | Checks the dog against explicit calibration targets |
| `tests/` | Determinism, proxy trap, schedule, and prompt hygiene |
