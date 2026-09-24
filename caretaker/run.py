"""Run the study. The one command to use.

    python -m caretaker.run --phase pilot --model mock        # free, scripted stand-in
    python -m caretaker.run --phase pilot --model anthropic   # real: shows cost, asks first

Test your own deployment instructions against the same 30 days:

    python -m caretaker.run --model anthropic --instructions my_instructions.txt

Your text becomes the caretaker's instructions, on top of the task itself. The dogs,
the illnesses, the owner's "skip the vet" requests and the silent failures are
identical to the study's runs, so results sit beside them in data/runs.csv.
Add --no-owner-instructions to run your text with an owner who asks for nothing.

Options:
    --conditions control constitutional   which conditions (default: the phase's)
    --seeds 11 12                         which seeds (default: the phase's)
    --days 2                              stop early: a short trial run, not study data
    --yes                                 skip the confirmation (only after approving the estimate)

Before any real run it prints the number of model calls and a cost range, then
waits for "yes". Logs go to logs/<phase>/ (real runs), logs/trial/ (--days) or
logs/mock/ (mock runs).
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from inspect_ai import eval as inspect_eval
from inspect_ai.model import GenerateConfig, get_model
from rich.console import Console

from caretaker.mock import mock_model
from caretaker.prompts import evaluation_words_in
from caretaker.simulator import ROOT, load_config
from caretaker.task import caretaker

CHARS_PER_TOKEN = 4          # rough rule of thumb for English text
REAL_REPLY_MARGIN = 1.5      # real replies are longer than the mock's, so memory grows faster
VISIBLE_OUTPUT_TOKENS = 300  # per call: the JSON reply, a review or a summary
THINKING_TOKENS = (500, 4000)  # per call, low and high guesses; billed as output


def main() -> int:
    runs = load_config("runs.yaml")
    parser = argparse.ArgumentParser(description="Run the study.")
    parser.add_argument("--phase", default="pilot", choices=list(runs["phases"]))
    parser.add_argument("--model", required=True, choices=list(runs["models"]))
    parser.add_argument("--conditions", nargs="+")
    parser.add_argument("--seeds", nargs="+", type=int)
    parser.add_argument("--days", type=int)
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--instructions", metavar="FILE",
                        help="your own deployment instructions; runs them as the 'custom' condition")
    parser.add_argument("--no-owner-instructions", action="store_true",
                        help="the owner asks for nothing: no 'skip the vet', no cost pressure")
    args = parser.parse_args()

    instructions_file = None
    if args.instructions:
        path = Path(args.instructions).expanduser().resolve()
        if not path.is_file():
            print(f"No such file: {path}")
            return 1
        text = path.read_text().strip()
        if not text:
            print(f"{path} is empty.")
            return 1
        instructions_file = str(path)
        given_away = evaluation_words_in(text)
        if given_away:
            print(f"Warning: your instructions contain {', '.join(given_away)}. A caretaker that can tell "
                  "it is being assessed behaves differently, so results may not reflect a real deployment.\n")

    phase_cfg = runs["phases"][args.phase]
    conditions = ["custom"] if instructions_file else (args.conditions or phase_cfg["conditions"])
    seeds = ",".join(str(s) for s in (args.seeds or phase_cfg["seeds"]))
    def make(condition: str):
        return caretaker(args.phase, condition, seeds=seeds, max_days=args.days,
                         instructions_file=instructions_file if condition == "custom" else None,
                         owner_instructions=not args.no_owner_instructions)

    tasks = [make(c) for c in conditions]

    if args.model == "mock":
        logs = run_eval(tasks, mock_model(), ROOT / "logs" / "mock")
        return report(logs) if logs is not None else 1

    model_id = runs["models"][args.model]
    if not model_id:
        print(f"No model ID set for {args.model} in config/runs.yaml.")
        return 1
    load_dotenv(ROOT / ".env")
    key_var = runs["api_key_env"][args.model]
    if not os.environ.get(key_var):
        print(f"{key_var} is not set. Copy .env.example to .env and add the key.")
        return 1

    print_estimate(args, model_id, conditions, seeds, runs["pricing"].get(args.model), make)
    if not args.yes and input("\nType yes to start: ").strip().lower() != "yes":
        print("Not started.")
        return 0

    log_dir = ROOT / "logs" / ("trial" if args.days else args.phase)
    logs = run_eval(tasks, model_id, log_dir)
    return report(logs) if logs is not None else 1


def limited(model):
    """The model with capped retries and a per-call timeout (see `limits` in runs.yaml)."""
    limits = load_config("runs.yaml")["limits"]
    config = GenerateConfig(max_retries=limits["api_max_retries"], timeout=limits["api_timeout_s"])
    return get_model(model, config=config) if isinstance(model, str) else model


def run_eval(tasks, model, log_dir, **kwargs):
    """Run Inspect, and say plainly why if it can't start (e.g. a missing package).

    Inspect's live display can swallow its own startup errors, which otherwise
    leaves a bare exit code and no explanation. Retries and time are capped so an
    account with no credit fails in minutes instead of hanging for days.
    """
    kwargs.setdefault("time_limit", load_config("runs.yaml")["limits"]["sample_time_limit_s"])
    try:
        return inspect_eval(tasks, model=limited(model), log_dir=str(log_dir), **kwargs)
    except Exception as error:
        # A fresh console bound to the current stdout: Inspect may have replaced the global one.
        Console(file=sys.stdout).print(f"\n[bold]The run could not start.[/bold]", getattr(error, "message", None) or repr(error))
        return None


def print_estimate(args, model_id: str, conditions: list[str], seeds: str, price: dict | None, make=None) -> None:
    # Dry-run the exact same tasks on the scripted mock (free) to count calls and prompt sizes.
    make = make or (lambda c: caretaker(args.phase, c, seeds=seeds, max_days=args.days))
    with tempfile.TemporaryDirectory() as tmp:
        tasks = [make(c) for c in conditions]
        logs = run_eval(tasks, mock_model(), tmp, display="none")
        if logs is None:
            raise SystemExit(1)
        calls, input_chars, per_condition = 0, 0, {}
        for log, condition in zip(logs, conditions):
            for sample in log.samples:  # read while the temporary logs still exist
                run = sample.store["run"]
                n = sum(len(d["calls"]) for d in run["days"]) + len(run["summaries"])
                per_condition[condition] = n
                calls += n
                for d in run["days"]:
                    # Each call resends the whole day's conversation so far.
                    conversation = len(d["system_prompt"]) + len(d["user_message"])
                    for i, c in enumerate(d["calls"]):
                        if i > 0:
                            conversation += len(d["calls"][i - 1]["response"]) + len(c["prompt"])
                        input_chars += conversation
                input_chars += sum(len(run["days"][0]["system_prompt"]) + len(s["call"]["prompt"])
                                   for s in run["summaries"])

    input_tokens = input_chars / CHARS_PER_TOKEN * REAL_REPLY_MARGIN
    output_low, output_high = (calls * (VISIBLE_OUTPUT_TOKENS + t) for t in THINKING_TOKENS)
    n_runs = len(conditions) * len(seeds.split(","))
    days = args.days or load_config("schedule.yaml")["phases"][args.phase]["days"]

    print(f"\n{args.phase} on {model_id}" + (" (TRIAL RUN, not study data)" if args.days else ""))
    print(f"  runs:         {n_runs} ({len(conditions)} conditions x {len(seeds.split(','))} seeds), {days} days each")
    print(f"  model calls:  {calls}  ({', '.join(f'{c} {n} per run' for c, n in per_condition.items())})")
    print(f"                up to {2 * calls} if every reply needed its one retry")
    print(f"  input:        about {input_tokens:,.0f} tokens")
    print(f"  output:       {output_low:,.0f} to {output_high:,.0f} tokens, including thinking")
    if price:
        low = (input_tokens * price["input"] + output_low * price["output"]) / 1e6
        high = (input_tokens * price["input"] + output_high * price["output"]) / 1e6
        print(f"  cost:         about ${low:.2f} to ${high:.2f}")
        print(f"                (prices in config/runs.yaml, as of {price['as_of']}; check current prices)")
    else:
        print("  cost:         no prices in config/runs.yaml for this vendor")


def report(logs) -> int:
    ok = True
    print()
    for log in logs:
        condition = log.eval.task_args.get("condition")
        print(f"{condition}: {log.status}  (log: {log.location})")
        if log.status != "success":
            ok = False
            print("  error:", log.error.message if log.error else "unknown")
            continue
        for sample in log.samples:
            v = sample.scores["care_metrics"].value
            compliance = v["harmful_compliance_rate"]
            compliance = "n/a" if math.isnan(compliance) else f"{compliance:.2f}"
            print(f"  {sample.id:<8} proxy gap {v['proxy_gap']:6.1f}   harmful compliance "
                  f"{compliance:>4}   questions/10 days {v['question_rate']:.1f}   "
                  f"final health {v['final_health']:5.1f}   parse failures {v['parse_failures']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
