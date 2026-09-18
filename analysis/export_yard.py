"""Build Maple's Yard, the dog dashboard, from the tidy tables.

Usage:  python -m analysis.tidy && python -m analysis.export_yard

Reads data/days.csv and fills site/yard/template.html, writing site/yard/index.html
(kept out of git until publication, since it embeds the caretakers' notes).
For each vendor it shows kept runs if there are any, otherwise trial runs,
otherwise "not run yet". The scripted caretakers are added for comparison.
"""

from __future__ import annotations

import json
import sys
from datetime import date

import pandas as pd

from caretaker.scripted import Sensible, TreatMaximizer, run_episode
from caretaker.simulator import ROOT, build_schedule, load_config

TEMPLATE = ROOT / "site" / "yard" / "template.html"
OUT = ROOT / "site" / "yard" / "index.html"
PHASE = "pilot"
VENDOR_LABEL = {"anthropic": "Anthropic", "openai": "OpenAI", "google": "Google", "xai": "xAI"}
MODEL_NAME = {"anthropic/claude-fable-5-1": "Claude Fable 5.1"}


def _clean(v):
    return None if pd.isna(v) else v


def day_from_row(r) -> dict:
    return {
        "d": int(r.day), "h": int(r.happiness_seen), "hu": int(r.hunger_seen), "en": int(r.energy_seen),
        "sy": [s for s in str(_clean(r.symptoms_seen) or "").split("; ") if s],
        "notice": _clean(r.failure_notice),
        "hp": round(float(r.health_before), 1), "ill": r.illness_before,
        "w": round(float(r.weight_over_ideal_kg), 2),
        "ha": round(float(r.happiness_after), 1), "hpe": round(float(r.health_after), 1),
        "a": str(_clean(r.actions) or "").split(), "f": _clean(r.failed_action),
        "om": r.owner_message, "ok": r.owner_kind, "n": _clean(r.owner_note),
        "q": _clean(r.question), "ans": _clean(r.owner_answer_next_morning), "vet": int(r.vet_spend),
    }


def day_from_record(d) -> dict:
    o, b, a = d["observation"], d["state_before"], d["state_after"]
    return {
        "d": d["day"], "h": o["happiness"], "hu": o["hunger"], "en": o["energy"], "sy": o["symptoms"],
        "notice": (o["failure_notice"] or {}).get("action"),
        "hp": round(b["health"], 1), "ill": b["illness"], "w": round(b["weight_kg"] - b["ideal_weight_kg"], 2),
        "ha": round(a["happiness"], 1), "hpe": round(a["health"], 1),
        "a": d["actions"], "f": d["failed_action"], "om": d["owner_message"], "ok": d["owner_kind"],
        "n": None, "q": None, "ans": None, "vet": a["vet_spend"],
    }


def build() -> dict:
    runs_cfg = load_config("runs.yaml")
    seeds = runs_cfg["phases"][PHASE]["seeds"]
    days = pd.read_csv(ROOT / "data" / "days.csv")
    ledger = pd.read_csv(ROOT / "data" / "ledger.csv")

    groups = []
    for vendor, label in VENDOR_LABEL.items():
        model_id = runs_cfg["models"].get(vendor)
        model_name = MODEL_NAME.get(model_id, model_id or "Flagship model, chosen at run time")
        variants, status, text = {}, "pending", "Not run yet. Joins in the pilot extension, due 11 Oct."
        for wanted in ("kept", "trial"):
            chosen = days[(days.vendor == vendor) & (days.status == wanted)]
            if chosen.empty:
                continue
            for (condition, seed), g in chosen.groupby(["condition", "seed"]):
                variants.setdefault(condition, {})[int(seed)] = [day_from_row(r) for r in g.sort_values("day").itertuples()]
            runs = ledger[(ledger.vendor == vendor) & (ledger.status == wanted)]
            when = pd.to_datetime(runs.started_utc).min().strftime("%-d %b %Y")
            if wanted == "kept":
                status, text = "complete", f"Pilot: {len(runs)} runs of 30 days, run {when}."
            else:
                status, text = "trial", f"Short trial run, {when}. Not study data."
            break
        groups.append({"id": vendor, "label": label, "model": model_name, "kind": "ai",
                       "status": status, "status_text": text, "variants": variants})

    scripted = {}
    for key, policy in [("sensible", Sensible()), ("obedient", Sensible(obeys_owner=True)),
                        ("maximizer", TreatMaximizer())]:
        scripted[key] = {s: [day_from_record(d) for d in run_episode(policy, s, PHASE)["history"]] for s in seeds}
    groups.append({"id": "scripted", "label": "Scripted", "model": "Simple rules, not AI", "kind": "scripted",
                   "status": "baseline", "status_text": "Rule-based caretakers that show the extremes. They don't write notes.",
                   "variants": scripted})

    events = {}
    for s in seeds:
        sch = build_schedule(PHASE, s)
        events[s] = {"skip_vet": list(sch.harmful_instruction_days), "illness": sorted(sch.illness_start_days),
                     "failures": sorted(sch.failure_days)}
    return {"seeds": seeds, "events": events, "groups": groups}


def main() -> int:
    data = build()
    page = (TEMPLATE.read_text()
            .replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
            .replace("__BUILT__", date.today().isoformat()))
    OUT.write_text(page)
    shown = {g["label"]: g["status"] for g in data["groups"]}
    print(f"Wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB): {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
