"""Weekly compression: summaries replace the week's details, on schedule."""

from caretaker.memory import Memory
from caretaker.prompts import load


def test_first_day_message():
    assert Memory().render() == load("memory_empty.txt")


def test_week_ends_every_seventh_day_but_not_the_last():
    ends = [d for d in range(1, 31) if Memory.week_ends(d, 30)]
    assert ends == [7, 14, 21, 28]
    assert not Memory.week_ends(28, 28)  # no summary once the run is over


def test_details_leave_after_summary():
    m = Memory()
    for day in range(1, 8):
        m.record_day(day, f"observation {day}", f"reply {day}")
    assert "observation 3" in m.render()
    m.close_week("Week one went fine.")
    text = m.render()
    assert "observation 3" not in text and "reply 7" not in text
    assert "Week one went fine." in text
    assert "days 1 to 7" in text


def test_summaries_accumulate_and_current_week_shows():
    m = Memory()
    for week in range(2):
        for day in range(week * 7 + 1, week * 7 + 8):
            m.record_day(day, f"obs {day}", "{}")
        m.close_week(f"summary {week + 1}")
    m.record_day(15, "obs 15", "{}")
    text = m.render()
    assert "summary 1" in text and "summary 2" in text and "obs 15" in text
    assert "obs 14" not in text


def test_summary_request_includes_the_week():
    m = Memory()
    m.record_day(1, "obs 1", "{}")
    request = m.summary_request("Maple")
    assert "obs 1" in request and "This week is over" in request
