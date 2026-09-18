"""Parse and check the caretaker's daily reply.

The reply must be one JSON object:
    {"actions": ["feed", "walk"], "owner_note": "...", "question": null}

Two leniencies, applied the same way to every vendor so formatting habits
don't count as behavior: a Markdown code fence around the JSON is ignored, and
the constitutional review step may write its review before the final JSON
(`allow_preamble`). Anything else that doesn't fit raises ReplyError, and the
message is shown to the caretaker when it gets its one retry.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from caretaker.simulator import ACTIONS, load_config

FENCE = re.compile(r"^```[a-zA-Z]*\s*(.*?)\s*```$", re.DOTALL)


class ReplyError(ValueError):
    pass


@dataclass
class Reply:
    actions: list[str]
    owner_note: str
    question: str | None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def parse_reply(text: str, allow_preamble: bool = False) -> Reply:
    data = _extract_json(text, allow_preamble)
    if not isinstance(data, dict):
        raise ReplyError("the reply is not a JSON object")

    actions = data.get("actions")
    if not isinstance(actions, list) or not all(isinstance(a, str) for a in actions):
        raise ReplyError('"actions" must be a list of action names')
    actions = [a.strip().lower() for a in actions]
    unknown = [a for a in actions if a not in ACTIONS]
    if unknown:
        raise ReplyError(f"unknown action(s): {', '.join(unknown)}")
    limit = load_config("dog.yaml")["max_actions_per_day"]
    if len(actions) > limit:
        raise ReplyError(f"at most {limit} actions per day")

    note = data.get("owner_note")
    if not isinstance(note, str) or not note.strip():
        raise ReplyError('"owner_note" must be a non-empty string')

    question = data.get("question")
    if question is not None and not isinstance(question, str):
        raise ReplyError('"question" must be a string or null')
    question = question.strip() if question else None
    asks = actions.count("ask_owner")
    if asks > 1:
        raise ReplyError("only one question per day")
    if asks and not question:
        raise ReplyError('"ask_owner" needs a question in "question"')
    if question and not asks:
        raise ReplyError('a question needs "ask_owner" in "actions"')

    return Reply(actions, note.strip(), question)


def _extract_json(text: str, allow_preamble: bool):
    body = text.strip()
    fenced = FENCE.match(body)
    if fenced:
        body = fenced.group(1)
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        if not allow_preamble:
            raise ReplyError("the reply is not valid JSON") from None

    # Review first, JSON last: take the last object that runs to the end of the text.
    decoder = json.JSONDecoder()
    tail = text.rstrip().removesuffix("```").rstrip()
    for start in reversed([i for i, ch in enumerate(tail) if ch == "{"]):
        try:
            data, end = decoder.raw_decode(tail, start)
        except json.JSONDecodeError:
            continue
        if not tail[end:].strip():
            return data
    raise ReplyError("no JSON object found at the end of the reply")
