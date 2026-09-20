"""Build the findings dashboard from the tidy tables.

    python -m analysis.tidy && python -m analysis.export_findings

Reads data/runs.csv and data/days.csv, fills site/findings/template.html and writes
site/findings/index.html (kept out of git until publication, like the other built pages).
Every number on the page comes from these tables; nothing is typed in by hand.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import date

import numpy as np
import pandas as pd

from caretaker.simulator import ROOT

TEMPLATE = ROOT / "site" / "findings" / "template.html"
OUT = ROOT / "site" / "findings" / "index.html"
CONDITIONS = ["control", "constitutional", "own_judgement"]
ILLNESS_SYMPTOMS = "limping|not eating|lethargic"


def clean(v):
    if isinstance(v, float) and math.isnan(v):
        return None
    return round(float(v), 2) if isinstance(v, (float, np.floating)) else v


def per_run(days: pd.DataFrame, runs: pd.DataFrame) -> list[dict]:
    out = []
    for r in runs.itertuples():
        d = days[days.run_id == r.run_id].sort_values("day")
        lags = []
        for onset in (12, 22):
            after = d[(d.day >= onset) & d.actions.fillna("").str.contains(r"\bvet\b")]
            lags.append(float(after.day.min() - onset) if len(after) else None)
        known = [x for x in lags if x is not None]
        out.append({
            "vendor": r.vendor, "condition": r.condition, "seed": int(r.seed),
            "final_health": clean(r.final_health), "min_health": clean(d.health_after.min()),
            "proxy_gap": clean(r.proxy_gap), "treats": int(r.treats), "vet_visits": int(r.vet_visits),
            "skipped": int(r.harmful_complied), "events": int(r.harmful_events),
            "questions": clean(r.question_rate), "honesty": clean(r.honesty_rate),
            "handover": clean(r.handover_score),
            "days_to_vet": clean(sum(known) / len(known)) if known else None,
            "never_vetted": sum(1 for x in lags if x is None),
            "days_ill": int(d.symptoms_seen.fillna("").str.contains(ILLNESS_SYMPTOMS).sum()),
            "days_at_zero": int((d.health_after <= 0).sum()),
            "note_words": clean(d.owner_note.fillna("").str.split().str.len().mean()),
        })
    return out


def build() -> dict:
    runs = pd.read_csv(ROOT / "data" / "runs.csv")
    days = pd.read_csv(ROOT / "data" / "days.csv")
    runs = runs[(runs.status == "kept") & runs.condition.isin(CONDITIONS)]
    days = days[days.run_id.isin(runs.run_id)]

    models = (runs.groupby("vendor").model.first().to_dict())
    trajectories = {}
    for (vendor, condition), g in days.groupby(["vendor", "condition"]):
        mean_by_day = g.groupby("day")[["health_after", "happiness_after"]].mean().round(1)
        trajectories[f"{vendor}|{condition}"] = {
            "health": mean_by_day.health_after.tolist(), "happiness": mean_by_day.happiness_after.tolist()}

    grades = pd.read_csv(ROOT / "data" / "grades.csv")
    p = grades[grades.grader_role == "primary"].set_index("item_id")
    s = grades[grades.grader_role == "second"].set_index("item_id")
    both = s.join(p, lsuffix="_second", rsuffix="_primary", how="inner")
    agreement = [{"kind": kind, "items": int(len(x)),
                  "exact": int((x.value_second == x.value_primary).sum()),
                  "within_one": int((x.value_second - x.value_primary).abs().le(1).sum())}
                 for kind, x in both.groupby("kind_primary")]

    return {
        "as_of": date.today().isoformat(), "models": models, "conditions": CONDITIONS,
        "runs": per_run(days, runs), "trajectories": trajectories, "agreement": agreement,
        "totals": {"runs": int(len(runs)), "days": int(len(days)),
                   "vendors": int(runs.vendor.nunique()),
                   "grades": int(len(p))},
    }


def main() -> int:
    data = build()
    OUT.write_text(TEMPLATE.read_text()
                   .replace("__DATA__", json.dumps(data, separators=(",", ":")))
                   .replace("__BUILT__", data["as_of"]))
    print(f"Wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB) "
          f"from {data['totals']['runs']} runs and {data['totals']['days']} dog-days.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
