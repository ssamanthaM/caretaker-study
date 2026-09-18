"""The reply checker accepts exactly the agreed format, with the two stated leniencies."""

import pytest

from caretaker.reply import ReplyError, parse_reply

GOOD = '{"actions": ["feed", "walk"], "owner_note": "All well.", "question": null}'


def test_accepts_valid_reply():
    r = parse_reply(GOOD)
    assert r.actions == ["feed", "walk"] and r.owner_note == "All well." and r.question is None


def test_accepts_code_fence():
    assert parse_reply(f"```json\n{GOOD}\n```").actions == ["feed", "walk"]


def test_accepts_empty_actions():
    assert parse_reply('{"actions": [], "owner_note": "Quiet day.", "question": null}').actions == []


def test_question_with_ask_owner():
    r = parse_reply('{"actions": ["feed", "ask_owner"], "owner_note": "Hi.", "question": "Treats OK?"}')
    assert r.question == "Treats OK?"


def test_preamble_only_when_allowed():
    text = "Review: principle 1 is met.\n" + GOOD
    with pytest.raises(ReplyError):
        parse_reply(text)
    assert parse_reply(text, allow_preamble=True).actions == ["feed", "walk"]


def test_preamble_takes_last_object():
    text = 'Draft was {"actions": ["treat"]}. Final:\n' + GOOD
    assert parse_reply(text, allow_preamble=True).actions == ["feed", "walk"]


@pytest.mark.parametrize("text, message", [
    ("Sure! I'll feed her.", "not valid JSON"),
    ('["feed"]', "not a JSON object"),
    ('{"actions": "feed", "owner_note": "x", "question": null}', "list of action"),
    ('{"actions": ["fly"], "owner_note": "x", "question": null}', "unknown action"),
    ('{"actions": ["feed", "feed", "walk", "play"], "owner_note": "x", "question": null}', "at most 3"),
    ('{"actions": ["feed"], "owner_note": "", "question": null}', "owner_note"),
    ('{"actions": ["feed"], "question": null}', "owner_note"),
    ('{"actions": ["ask_owner"], "owner_note": "x", "question": null}', "needs a question"),
    ('{"actions": ["feed"], "owner_note": "x", "question": "Why?"}', 'needs "ask_owner"'),
    ('{"actions": ["ask_owner", "ask_owner"], "owner_note": "x", "question": "a"}', "one question"),
])
def test_rejects(text, message):
    with pytest.raises(ReplyError, match=message):
        parse_reply(text)
