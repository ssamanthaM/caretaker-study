"""A scripted stand-in for a model, so the whole pipeline runs end to end for free.

Plugged into Inspect's mock provider (mockllm/model). It reads the prompt it is
sent and answers in the required format: a weekly summary when asked for one,
a review plus JSON on the constitutional review step, and otherwise a sensible
day's plan (vet if the dog shows illness symptoms). It is test scaffolding and
never produces study data.
"""

from __future__ import annotations

import json
import re

from inspect_ai.model import ModelOutput, get_model

from caretaker.prompts import fill
from caretaker.simulator import load_config

_SUMMARY_CUE = fill("memory_summary.txt", dog_name=load_config("dog.yaml")["name"]).split(".")[0]
_REVIEW_CUE = fill("constitutional_critique.txt").split(".")[0]
_ILLNESS = {s for group in load_config("dog.yaml")["illness"]["symptoms"] for s in group}


def scripted_caretaker(messages, tools, tool_choice, config) -> ModelOutput:
    last = messages[-1].text
    if _SUMMARY_CUE in last:
        return _out("Quiet week. Fed and walked her daily; took her to the vet when she was unwell.")

    # The morning observation is in the first user message of the day.
    day_text = next(m.text for m in messages if m.role == "user")
    symptoms = re.findall(r"- Symptoms: (.*)", day_text)[-1]
    ill = any(s in symptoms for s in _ILLNESS)
    reply = {"actions": ["vet", "feed", "walk"] if ill else ["feed", "walk", "play"],
             "owner_note": "She was unwell, so I took her to the vet." if ill
             else "Fed her, walked her and played with her. She seems well.",
             "question": None}
    text = json.dumps(reply)
    if _REVIEW_CUE in last:
        text = "Review: the draft meets all six principles.\n" + text
    return _out(text)


def _out(text: str) -> ModelOutput:
    return ModelOutput.from_content(model="mockllm/model", content=text)


def mock_model():
    return get_model("mockllm/model", custom_outputs=scripted_caretaker, memoize=False)
