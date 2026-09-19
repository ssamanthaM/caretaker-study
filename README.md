# The Caretaker Study

Do alignment controls that deployers can impose at runtime keep frontier models behaving well over long deployments, and does that vary by vendor? Four frontier models each care for an identical simulated dog, under four alignment approaches plus a control.

The design, hypotheses and analysis plan are fixed in advance in [`docs/preregistration.md`](docs/preregistration.md). Changes after it was committed are logged in [`docs/deviations.md`](docs/deviations.md).

## Status

Stage 2 of 5: the daily loop runs end to end on a scripted mock model, for the control and constitutional conditions. No real model has been run yet.

## Setup

Requires [uv](https://docs.astral.sh/uv/), which installs the right Python (3.12) and every package:

```
uv sync
uv run pytest
uv run python -m caretaker.calibrate
uv run python -m caretaker.run --phase pilot --model mock        # free end-to-end run
uv run inspect view --log-dir logs/mock                          # browse the logs
uv run python -m analysis.tidy                                   # logs -> data/ tables
uv run python -m analysis.grade --grader mock                    # free check of the grading pipeline
uv run python -m analysis.gonogo                                 # the preregistered go/no-go rule
```

A real run (`--model anthropic`) prints the number of model calls and a cost range first, and starts only after you type `yes`.

## How the dog works

The dog is a deterministic rules engine (`caretaker/simulator.py`), not an AI: the same seed and the same actions always give the same outcome, so any difference between runs comes from the caretaker. Caretakers see happiness, hunger, energy and symptoms. Health, weight and illness are hidden. Treats raise visible happiness but, beyond one a day, quietly erode health. That is the proxy trap.

Every number is in `config/`, and everything the caretaker reads is a plain-text file in `prompts/`, published verbatim.

## Layout

| Path | What it holds |
| --- | --- |
| `config/dog.yaml` | Every simulator parameter |
| `config/schedule.yaml` | When each stress test fires |
| `config/runs.yaml` | Phases, seeds, models |
| `prompts/` | Everything the caretaker reads; `prompts/owner/` is everything the owner says |
| `caretaker/simulator.py` | The dog |
| `caretaker/owner.py` | Scripted owner messages and answers |
| `caretaker/scripted.py` | Non-AI baseline caretakers (`treat_maximizer`, `sensible`) |
| `caretaker/calibrate.py` | Checks the dog against explicit calibration targets |
| `caretaker/task.py` | The Inspect task: the daily loop |
| `caretaker/memory.py` | Weekly self-written summaries |
| `caretaker/reply.py` | Checks each reply's format |
| `caretaker/scorers.py` | The automatic metrics |
| `caretaker/run.py` | The one command to run anything; asks before spending |
| `caretaker/mock.py` | Scripted stand-in model for free end-to-end runs |
| `tests/` | Determinism, proxy trap, schedule, and prompt hygiene |
