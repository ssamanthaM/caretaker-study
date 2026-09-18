# Learning log

## 2026-09-18: Stage 1, the dog

**Built.** Repo skeleton; `config/` (dog, schedule, runs); the simulator; the scripted owner and its message files; two scripted caretakers; a calibration script; 40 tests.

**Decisions made.**
- Silent failures never hit vet or ask_owner, and never land on illness or harmful-instruction days or the final day. The failure notice arrives the next morning, and that day's owner note is the one graded.
- Illness only precedes the harmful-instruction days.
- Every condition sees happiness as a number; reward feedback adds only the rating and the instruction.
- Illness starts silently the day before the instruction. Symptoms first show on the instruction morning. Otherwise a diligent caretaker cures the dog before the owner ever says "skip the vet".

**Concepts.**
- *Determinism and seeds.* Every random draw comes from `random.Random("seed:purpose")` and is made before day 1. So the dog, the events and the owner's words can't depend on what the caretaker does.
- *Separate random streams.* One stream per purpose (dog, noise, failures, owner), so adding a draw to one never shifts the others.
- *Calibration as a test.* "Neither perfect nor hopeless" became numeric targets in `calibrate.py`, checked on held-out seeds (1001–1010) so the dog isn't tuned to the study's own seeds.
- *Tests catch real bugs.* The owner matched "eat" inside "weather"; keyword matching now only looks at the start of words.

**Commands.**
- `uv sync` installs Python 3.12 and every package into `.venv/`.
- `uv run pytest` runs all tests.
- `uv run python -m caretaker.calibrate` prints the calibration table.

## 2026-09-18: Stage 2, the daily loop

**Built.** The caretaker-facing prompts; the Inspect task and daily loop (`task.py`); reply checking with one retry (`reply.py`); weekly memory compression (`memory.py`); the four automatic metrics (`scorers.py`); a scripted mock model (`mock.py`); and `run.py`, which prints calls and cost before any paid run. 74 tests.

**Decisions made.**
- Pilot model: Claude Fable 5.1. "Flagship" means each vendor's most capable generally available model; no automatic fallbacks to other models.
- Provider defaults for generation settings (Inspect allows Fable 5.1 up to 32,000 output tokens).
- A code fence around the JSON is accepted; the constitutional review may write its review before the final JSON.
- Memory shows the current week in full plus summaries of earlier weeks.

**Concepts.**
- *Solver and scorer.* In Inspect, the solver does the work (here, 30 days of calls) and the scorer turns the result into numbers.
- *Mock model.* A stand-in that answers in the right format for free, so the whole pipeline can be checked before spending anything.
- *NaN, not zero.* A short trial run has no harmful-instruction events, so its compliance rate is "not applicable" (NaN), not 0.

**Commands.**
- `uv run python -m caretaker.run --phase pilot --model mock` runs the free end-to-end pilot.
- `uv run python -m caretaker.run --phase pilot --model anthropic --days 2 --seeds 11` runs a short paid trial run (asks first).
- `uv run inspect view --log-dir logs/mock` opens Inspect's log viewer in the browser.

## 2026-09-18: The pilot, and tracking the data

**Built.** `analysis/tidy.py` turns every log into three tables in `data/`: a run ledger (one row per run, with status, code commit and cost), the preregistered metrics per run, and one row per dog-day. `analysis/export_yard.py` rebuilds the Maple's Yard dashboard from those tables. 85 tests.

**What happened.**
- The first pilot attempt ran out of Anthropic credit halfway. Its control runs exposed an owner-script flaw: asking about the vet got "Use your judgement", which cancelled the harmful instruction. Fixed and logged in `docs/deviations.md`; the old runs are kept in `logs/pilot-discarded-2026-09-18/`.
- The re-run pilot completed: 6 runs, no parse failures, about $19.68. The go/no-go rule is met on the automatic metrics (question rate is higher under constitutional for all 3 dogs); honesty and handover still need grading in Stage 3.

**Concepts.**
- *Nothing deleted, only filed.* A run's status comes from its log folder (kept, discarded, trial), so dead ends stay on the record.
- *One source for every number.* Tables are built from logs by code; the dashboard and the paper read the tables, never hand-copied figures.

**Commands.**
- `uv run python -m analysis.tidy` rebuilds the tables and prints the ledger.
- `uv run python -m analysis.export_yard` rebuilds the dashboard page.
