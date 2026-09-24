"""Turn Inspect logs into three tidy tables. The single source for every number reported.

Usage:  python -m analysis.tidy            # reads logs/, writes data/, prints the ledger

Writes to data/:
  ledger.csv  one row per run: what ran, when, on which code, its status and its cost
  runs.csv    one row per run: the preregistered metrics (graded ones once graded)
  days.csv    one row per run-day: what the caretaker saw, did and wrote, and the hidden state
  grades.csv  one row per graded item, from logs/grades/<role>/ (see analysis/grade.py)

A run's status comes from the folder its log sits in, so nothing is ever deleted,
only filed: logs/pilot, logs/full, logs/pilot_extension -> "kept";
logs/<phase>-discarded-<date> -> "discarded"; logs/trial -> "trial".
logs/mock is skipped (scripted stand-in, never data).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd
from inspect_ai.log import read_eval_log

from caretaker.scorers import compute_metrics, harmful_instruction_events
from caretaker.simulator import ROOT, load_config

LOGS = ROOT / "logs"
DATA = ROOT / "data"
KEPT_FOLDERS = {"pilot", "pilot_extension", "full"}


def status_for(folder: str) -> str | None:
    if folder in KEPT_FOLDERS:
        return "kept"
    if "-discarded-" in folder:
        return "discarded"
    if folder == "trial":
        return "trial"
    return None  # mock and anything unrecognised


def run_cost(usage: dict, price: dict | None) -> float | None:
    if not price:
        return None
    return (usage["input_tokens"] * price["input"]
            + usage["cache_write_tokens"] * price.get("cache_write", price["input"])
            + usage["cache_read_tokens"] * price.get("cache_read", price["input"])
            + usage["output_tokens"] * price["output"]) / 1e6


def tidy(logs_dir: Path = LOGS) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    runs_cfg = load_config("runs.yaml")
    ledger, runs, days = [], [], []

    for path in sorted(logs_dir.glob("*/*.eval")):
        status = status_for(path.parent.name)
        if status is None:
            continue
        log = read_eval_log(str(path))
        args = log.eval.task_args
        model = log.eval.model
        provider = model.split("/")[0]
        vendor = next((k for k, v in runs_cfg["models"].items() if v == model), provider)
        commit = log.eval.revision.commit[:7] if log.eval.revision else None

        for sample in log.samples or []:
            seed = sample.metadata.get("seed")
            run = sample.store.get("run") if sample.store else None
            day_records = run["days"] if run else []
            run_id = f"{vendor}_{args['condition']}_s{seed}_{log.eval.eval_id[:6]}"

            usage = {"input_tokens": 0, "cache_write_tokens": 0, "cache_read_tokens": 0,
                     "output_tokens": 0, "reasoning_tokens": 0}
            for u in (sample.model_usage or {}).values():
                usage["input_tokens"] += u.input_tokens or 0
                usage["cache_write_tokens"] += u.input_tokens_cache_write or 0
                usage["cache_read_tokens"] += u.input_tokens_cache_read or 0
                usage["output_tokens"] += u.output_tokens or 0
                usage["reasoning_tokens"] += u.reasoning_tokens or 0
            calls = (sum(len(d["calls"]) for d in day_records) + len(run["summaries"])) if run else 0
            cost = run_cost(usage, runs_cfg["pricing"].get(vendor))

            ledger.append({
                "run_id": run_id, "status": status if not sample.error else f"{status} (error)",
                "phase": args["phase"], "vendor": vendor, "model": model,
                "condition": args["condition"], "seed": seed,
                "days_run": len(day_records), "days_planned": run["schedule"]["days"] if run else None,
                "started_utc": log.stats.started_at, "completed_utc": log.stats.completed_at,
                "git_commit": commit, "model_calls": calls, **usage,
                "est_cost_usd": round(cost, 2) if cost is not None else None,
                "custom_instructions_sha256": (run or {}).get("custom_instructions_sha256"),
                "error": sample.error.message[:200] if sample.error else None,
                "log_file": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
            })
            if not day_records:
                continue

            instruction_days = run["schedule"]["harmful_instruction_days"]
            window = run["compliance_window_days"]
            metrics = compute_metrics(day_records, instruction_days, window)
            events = harmful_instruction_events(day_records, instruction_days, window)
            runs.append({
                "run_id": run_id, "status": status, "phase": args["phase"], "vendor": vendor,
                "model": model, "condition": args["condition"], "seed": seed,
                "days_run": len(day_records), **metrics,
                "harmful_events": len([e for e in events if e["applicable"]]),
                "harmful_complied": sum(1 for e in events if e["complied"]),
                "questions": sum(1 for d in day_records if d.get("question")),
                "vet_visits": sum(1 for d in day_records if "vet" in d["actions"]),
                "vet_spend": day_records[-1]["state_after"]["vet_spend"],
                "treats": sum(d["actions"].count("treat") for d in day_records),
                "silent_failures": sum(1 for d in day_records if d["failed_action"]),
            })
            for d in day_records:
                obs, before, after = d["observation"], d["state_before"], d["state_after"]
                reply = d.get("reply") or {}
                days.append({
                    "run_id": run_id, "status": status, "vendor": vendor, "condition": args["condition"],
                    "seed": seed, "day": d["day"],
                    "happiness_seen": obs["happiness"], "hunger_seen": obs["hunger"], "energy_seen": obs["energy"],
                    "symptoms_seen": "; ".join(obs["symptoms"]),
                    "failure_notice": (obs["failure_notice"] or {}).get("action"),
                    "owner_kind": d["owner_kind"], "owner_message": d["owner_message"],
                    "actions": " ".join(d["actions"]), "failed_action": d["failed_action"],
                    "parse_ok": d["parse_ok"], "owner_note": reply.get("owner_note"),
                    "question": d.get("question"), "owner_answer_next_morning": d.get("owner_answer_next_morning"),
                    "health_before": before["health"], "health_after": after["health"],
                    "happiness_before": before["happiness"], "happiness_after": after["happiness"],
                    "illness_before": before["illness"], "illness_after": after["illness"],
                    "weight_over_ideal_kg": round(before["weight_kg"] - before["ideal_weight_kg"], 3),
                    "vet_spend": after["vet_spend"], "model_calls": len(d["calls"]),
                })

    return pd.DataFrame(ledger), pd.DataFrame(runs), pd.DataFrame(days)


def tidy_grades(logs_dir: Path = LOGS) -> pd.DataFrame:
    """Every graded item, from every grader log. The folder names the grader's role."""
    rows = []
    for path in sorted((logs_dir / "grades").glob("*/*.eval")):
        log = read_eval_log(str(path))
        for sample in log.samples or []:
            score = (sample.scores or {}).get("read_grade")
            if score is None:
                continue
            value = score.value if isinstance(score.value, (int, float)) and not math.isnan(score.value) else None
            rows.append({
                "item_id": sample.id, "grader_role": path.parent.name, "grader_model": log.eval.model,
                "graded_utc": log.stats.started_at, **{k: sample.metadata.get(k) for k in
                ("run_id", "vendor", "condition", "seed", "status", "kind", "day", "action", "no_note")},
                "value": value, "detail": score.answer, "prompt": sample.input,
                "grader_response": sample.output.completion if sample.output else None,
                "log_file": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
            })
    grades = pd.DataFrame(rows)
    if not grades.empty:
        # If an item was graded more than once by the same role, the latest grade counts.
        grades = grades.sort_values("graded_utc").drop_duplicates(["item_id", "grader_role"], keep="last")
    return grades


def add_graded_metrics(runs: pd.DataFrame, grades: pd.DataFrame) -> pd.DataFrame:
    """Honesty rate, handover score and the awareness flag per run, from the primary grader."""
    if runs.empty or grades.empty or not (grades.grader_role == "primary").any():
        return runs
    g = grades[grades.grader_role == "primary"]
    per_run = pd.DataFrame({
        "honesty_rate": g[g.kind == "honesty"].groupby("run_id").value.mean(),
        "honesty_items": g[g.kind == "honesty"].groupby("run_id").value.count(),
        "handover_score": g[g.kind == "handover"].groupby("run_id").value.first(),
        "refers_to_being_tested": g[g.kind == "awareness"].groupby("run_id").value.first(),
    })
    return runs.merge(per_run, left_on="run_id", right_index=True, how="left")


def main() -> int:
    ledger, runs, days = tidy()
    grades = tidy_grades()
    runs = add_graded_metrics(runs, grades)
    DATA.mkdir(exist_ok=True)
    ledger.to_csv(DATA / "ledger.csv", index=False)
    runs.to_csv(DATA / "runs.csv", index=False)
    days.to_csv(DATA / "days.csv", index=False)
    grades.to_csv(DATA / "grades.csv", index=False)

    if ledger.empty:
        print("No runs found in logs/.")
        return 0
    cols = ["run_id", "status", "days_run", "model_calls", "est_cost_usd", "git_commit"]
    with pd.option_context("display.width", 140, "display.max_rows", 200):
        print(ledger[cols].to_string(index=False))
    print()
    for status, group in ledger.groupby("status"):
        cost = group["est_cost_usd"].sum()
        print(f"{status:<18} {len(group):>3} runs   about ${cost:,.2f}")
    print(f"\nWrote {len(ledger)} ledger rows, {len(runs)} run rows, {len(days)} day rows "
          f"and {len(grades)} grades to data/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
