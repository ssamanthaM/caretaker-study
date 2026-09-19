"""The owner: scripted messages and scripted answers.

The owner is not a model. What she says each day depends only on the schedule
and the seed, never on what the caretaker did, so every cell with the same seed
hears the same owner. All wording lives in prompts/owner/.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from caretaker.simulator import ROOT, Schedule, load_config, seeded_rng

OWNER_PROMPTS = ROOT / "prompts" / "owner"


def _lines(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


def daily_rating(happiness: float) -> int:
    """Owner's 1-5 star rating for the reward-feedback condition.

    Derived from visible happiness only, never health: the rating is the proxy.
    """
    return 1 + min(4, int(happiness) // 20)


class Owner:
    def __init__(self, schedule: Schedule, seed: int, dog_name: str | None = None,
                 prompts_dir: Path = OWNER_PROMPTS, gives_instructions: bool = True):
        # gives_instructions=False (the "own judgement" arm): the owner never says to skip
        # the vet and never pushes costs; every such day gets a routine message instead.
        # The dog's illnesses and silent failures stay on the same days.
        self.gives_instructions = gives_instructions
        self.schedule = schedule
        self.name = dog_name or load_config("dog.yaml")["name"]
        self.routine = _lines(prompts_dir / "routine.txt")
        self.skip_vet = _lines(prompts_dir / "skip_vet.txt")
        self.handover = (prompts_dir / "handover.txt").read_text().strip()
        levels = max(schedule.pressure_levels.values(), default=0)
        self.pressure = {n: _lines(prompts_dir / f"pressure_{n}.txt") for n in range(1, levels + 1)}
        with open(prompts_dir / "answers.yaml") as f:
            self.answers = yaml.safe_load(f)
        self.window = load_config("schedule.yaml")["compliance_window_days"]

        # Pre-draw a variant index for every day, whether or not it gets used,
        # so the owner's words never depend on the caretaker's choices.
        rng = seeded_rng(seed, "owner")
        self._variant = [rng.random() for _ in range(schedule.days + 1)]

    def kind(self, day: int) -> str:
        if day == self.schedule.handover_day:
            return "handover"
        if self.gives_instructions and day in self.schedule.harmful_instruction_days:
            return "harmful_instruction"
        if self.gives_instructions and day in self.schedule.pressure_levels:
            return "pressure"
        return "routine"

    def message(self, day: int) -> str:
        kind = self.kind(day)
        if kind == "handover":
            text = self.handover
        elif kind == "harmful_instruction":
            # Cycle through variants in order so repeat instructions don't read identically.
            occurrence = self.schedule.harmful_instruction_days.index(day)
            text = self.skip_vet[occurrence % len(self.skip_vet)]
        elif kind == "pressure":
            text = self._pick(self.pressure[self.schedule.pressure_levels[day]], day)
        else:
            text = self._pick(self.routine, day)
        return text.replace("{name}", self.name)

    def answer(self, question: str, day: int) -> str:
        """The owner's reply to a question asked on `day` (shown the next morning)."""
        topic = self._topic(question)
        if topic is None:
            return self.answers["fallback"]
        if "answer_while_skipping_vet" in topic and self.skipping_vet(day):
            # The instruction stays in force whether or not the caretaker asks.
            return topic["answer_while_skipping_vet"]
        return topic["answer"]

    def skipping_vet(self, day: int) -> bool:
        """True from each "skip the vet" instruction through its compliance window."""
        return self.gives_instructions and any(
            start <= day < start + self.window for start in self.schedule.harmful_instruction_days)

    def _topic(self, question: str) -> dict | None:
        # Keywords match at the start of a word, so "eat" matches "eating" but not
        # "weather". Most hits wins; ties go to the topic listed first.
        best, best_hits = None, 0
        for topic in self.answers["topics"]:
            hits = sum(1 for k in topic["keywords"]
                       if re.search(rf"\b{re.escape(k)}", question, re.IGNORECASE))
            if hits > best_hits:
                best, best_hits = topic, hits
        return best

    def _pick(self, options: list[str], day: int) -> str:
        return options[int(self._variant[day] * len(options))]
