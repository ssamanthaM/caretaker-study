# The Caretaker Study

Do alignment controls that deployers can impose at runtime keep frontier models behaving well over long deployments, and does that vary by vendor? Four frontier models each care for an identical simulated dog, under four alignment approaches plus a control.

The design, hypotheses and analysis plan are fixed in advance in [`docs/preregistration.md`](docs/preregistration.md). Changes after it was committed are logged in [`docs/deviations.md`](docs/deviations.md).

## Status

Stage 3 of 5, as of 17 November 2026. The pilot has been run on real models and graded; the full grid has not started.

- **Run.** 27 pilot runs of 30 days each on three vendors' models (Claude Fable 5.1, GPT-6 Astra, Gemini 3.8 Flash): the control and constitutional conditions on 3 dogs each, plus an exploratory "own judgement" arm. Every run, including discarded and trial runs, is kept in the run ledger, which stays private with the logs until publication.
- **Graded.** Honesty, handover and awareness notes are scored by a model grader, with a second grader from another vendor on a sample.
- **Go/no-go.** The preregistered rule (`analysis/gonogo.py`) returns go for each of the three models run, with every primary metric graded.
- **Written up.** A pilot paper is in [`paper/`](paper/), dated 20 September 2026. It is a pilot: 3 dogs per cell and no confirmatory statistics.

Not done yet:

- **xAI has not been run.** Its model is chosen and configured; the pilot covers three of the four preregistered vendors.
- **The hand-check of the grader is incomplete.** The preregistration commits to hand-scoring 10% of graded items; 4 items are scored so far, and the two model graders agreed exactly on 1 of 5 handovers. Treat the honesty and handover figures as provisional until this is finished.
- **2 of 5 conditions and 30 of the planned 100 days** have been run.
- The one-page findings note is not written, and the October milestones in the preregistration were missed. See [`docs/deviations.md`](docs/deviations.md).

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

## Test your own deployment instructions

Put the instructions you give your own AI assistant in a text file, then:

```
uv run python -m caretaker.run --model anthropic --instructions my_instructions.txt
```

Your text becomes the caretaker's instructions on top of the task itself. The dogs, the illnesses, the owner's "skip the vet" requests and the silent failures are identical to the study's own runs, so your results land in `data/runs.csv` beside them and can be compared directly. Add `--no-owner-instructions` to see what your instructions do with an owner who asks for nothing, and `--model mock --days 3` to rehearse the whole thing for free. See `examples/deployer_instructions_example.txt`.

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
| `caretaker/grader.py` | The grading task for honesty, handover and awareness |
| `prompts/rubrics/` | The grader's written rubrics, published verbatim |
| `analysis/` | Logs to tables (`tidy`), grading (`grade`), the go/no-go rule (`gonogo`), and the paper and dashboard builders |
| `paper/` | The pilot paper and its figures |
| `docs/` | Preregistration, deviations log, commit map |
| `tests/` | Determinism, proxy trap, schedule, and prompt hygiene |
