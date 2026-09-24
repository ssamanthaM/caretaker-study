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

# Nothing the caretaker reads may contain these: a model that knows it is being
# evaluated behaves differently (see the preregistration's threats to validity).
EVALUATION_WORDS = ("test", "evaluation", "experiment", "benchmark", "study")


def evaluation_words_in(text: str) -> list[str]:
    """Which give-away words appear in this text, if any."""
    import re
    return [w for w in EVALUATION_WORDS
            if re.search(rf"\b{w[:-1] if w.endswith('y') else w}(s|ies|y)?\b", text, re.I)]


@cache
def load(name: str) -> str:
    return (PROMPTS_DIR / name).read_text().rstrip("\n")


def fill(name: str, **values) -> str:
    return Template(load(name)).substitute(values)


@cache
def failure_notice(action: str) -> str:
    with open(PROMPTS_DIR / "failure_notices.yaml") as f:
        return yaml.safe_load(f)[action]


def system_prompt(condition: str, custom_instructions: str | None = None) -> str:
    """Base task plus the condition's own instructions (control adds none).

    `custom_instructions` is a deployer's own text (see `--instructions` in
    caretaker/run.py). It is used verbatim, apart from $dog_name and $vet_cost,
    which are filled in if present; any other $ is left alone.
    """
    dog = load_config("dog.yaml")
    values = {"dog_name": dog["name"], "vet_cost": dog["actions"]["vet"]["cost"]}
    condition_text = (Template(custom_instructions).safe_substitute(values) if custom_instructions is not None
                      else fill(f"{condition}.txt", **values))
    parts = [fill("base_task.txt", **values), condition_text.strip()]
    return "\n\n".join(p for p in parts if p)
