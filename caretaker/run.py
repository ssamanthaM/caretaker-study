"""Run the study. The one command to use.

    python -m caretaker.run --phase pilot --model mock        # free, scripted stand-in
    python -m caretaker.run --phase pilot --model anthropic   # real: shows cost, asks first

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
import os
import sys
import tempfile

from dotenv import load_dotenv
from inspect_ai import eval as inspect_eval

from caretaker.mock import mock_model
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
    args = parser.parse_args()

    phase_cfg = runs["phases"][args.phase]
    conditions = args.conditions or phase_cfg["conditions"]
    seeds = ",".join(str(s) for s in (args.seeds or phase_cfg["seeds"]))
    tasks = [caretaker(args.phase, c, seeds=seeds, max_days=args.days) for c in conditions]

    if args.model == "mock":
        logs = inspect_eval(tasks, model=mock_model(), log_dir=str(ROOT / "logs" / "mock"))
        return report(logs)

    model_id = runs["models"][args.model]
    if not model_id:
        print(f"No model ID set for {args.model} in config/runs.yaml.")
        return 1
    load_dotenv(ROOT / ".env")
    key_var = runs["api_key_env"][args.model]
    if not os.environ.get(key_var):
        print(f"{key_var} is not set. Copy .env.example to .env and add the key.")
        return 1

    print_estimate(args, model_id, conditions, seeds, runs["pricing"].get(args.model))
    if not args.yes and input("\nType yes to start: ").strip().lower() != "yes":
        print("Not started.")
        return 0

    log_dir = ROOT / "logs" / ("trial" if args.days else args.phase)
    logs = inspect_eval(tasks, model=model_id, log_dir=str(log_dir))
    return report(logs)


def print_estimate(args, model_id: str, conditions: list[str], seeds: str, price: dict | None) -> None:
    # Dry-run the exact same tasks on the scripted mock (free) to count calls and prompt sizes.
    with tempfile.TemporaryDirectory() as tmp:
        tasks = [caretaker(args.phase, c, seeds=seeds, max_days=args.days) for c in conditions]
        logs = inspect_eval(tasks, model=mock_model(), log_dir=tmp, display="none")
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
            print(f"  {sample.id:<8} proxy gap {v['proxy_gap']:6.1f}   harmful compliance "
                  f"{v['harmful_compliance_rate']:.2f}   questions/10 days {v['question_rate']:.1f}   "
                  f"final health {v['final_health']:5.1f}   parse failures {v['parse_failures']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
