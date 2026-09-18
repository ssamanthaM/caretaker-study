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
