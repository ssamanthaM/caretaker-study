"""Load and fill the prompt files in prompts/.

Every word the caretaker model reads comes from a file in prompts/, which is
published verbatim. Blanks are marked $name and filled with string.Template;
`substitute` raises if any blank is left unfilled, so a half-built prompt can
never reach a model.
"""

from __future__ import annotations

from functools import cache
from string import Template

import yaml

from caretaker.simulator import ROOT, load_config

PROMPTS_DIR = ROOT / "prompts"


@cache
def load(name: str) -> str:
    return (PROMPTS_DIR / name).read_text().rstrip("\n")


def fill(name: str, **values) -> str:
    return Template(load(name)).substitute(values)


@cache
def failure_notice(action: str) -> str:
    with open(PROMPTS_DIR / "failure_notices.yaml") as f:
        return yaml.safe_load(f)[action]


def system_prompt(condition: str) -> str:
    """Base task plus the condition's own instructions (control adds none)."""
    dog = load_config("dog.yaml")
    values = {"dog_name": dog["name"], "vet_cost": dog["actions"]["vet"]["cost"]}
    parts = [fill("base_task.txt", **values), fill(f"{condition}.txt", **values)]
    return "\n\n".join(p for p in parts if p)
