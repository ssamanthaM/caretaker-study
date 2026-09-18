"""The caretaker's memory: its own weekly summaries plus the current week in full.

At the end of every 7-day week the caretaker summarizes the week in its own
words (prompts/memory_summary.txt), and that week's daily details leave its
context for good. Anything it doesn't carry forward in a summary is forgotten,
which is what RQ3 (maintenance over long deployments) depends on.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from caretaker.prompts import fill, load

DAYS_PER_WEEK = 7


@dataclass
class Memory:
    summaries: list[dict] = field(default_factory=list)  # {week, first_day, last_day, text}
    this_week: list[dict] = field(default_factory=list)  # {day, observation, reply}

    def record_day(self, day: int, observation: str, reply: str) -> None:
        self.this_week.append({"day": day, "observation": observation, "reply": reply})

    @staticmethod
    def week_ends(day: int, last_day: int) -> bool:
        # No summary after the final day: the run is over.
        return day % DAYS_PER_WEEK == 0 and day < last_day

    def render(self) -> str:
        if not self.summaries and not self.this_week:
            return load("memory_empty.txt")
        parts = []
        if self.summaries:
            parts.append(load("memory_header.txt"))
            parts += [fill("memory_week.txt", week=s["week"], first_day=s["first_day"],
                           last_day=s["last_day"], summary=s["text"]) for s in self.summaries]
        if self.this_week:
            if parts:
                parts.append("")
            parts.append(load("memory_this_week.txt"))
            parts += [fill("memory_day.txt", day=d["day"], observation=d["observation"],
                           reply=d["reply"]) + "\n" for d in self.this_week]
        return "\n".join(parts).rstrip()

    def summary_request(self, dog_name: str) -> str:
        return self.render() + "\n\n" + fill("memory_summary.txt", dog_name=dog_name)

    def close_week(self, summary: str) -> None:
        self.summaries.append({
            "week": len(self.summaries) + 1,
            "first_day": self.this_week[0]["day"],
            "last_day": self.this_week[-1]["day"],
            "text": summary.strip(),
        })
        self.this_week = []
