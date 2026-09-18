"""End to end on the mock model: the full loop, the log, the scores, and prompt hygiene."""

import math

import pytest
from inspect_ai import eval as inspect_eval

from caretaker.mock import mock_model
from caretaker.simulator import DogSimulator, build_schedule
from caretaker.task import caretaker
from tests.test_hygiene import _contains_forbidden

HIDDEN_KEYS = {"health", "weight_kg", "illness"}


def _run(tmp_path, condition, model=None, **kwargs):
    log = inspect_eval(caretaker("pilot", condition, seeds="11", **kwargs),
                       model=model or mock_model(), log_dir=str(tmp_path), display="none")[0]
    assert log.status == "success", log.error
    return log, log.samples[0]


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("logs")
    return {c: _run(tmp, c) for c in ("control", "constitutional")}


@pytest.mark.parametrize("condition, per_day", [("control", 1), ("constitutional", 2)])
def test_call_counts(runs, condition, per_day):
    run = runs[condition][1].store["run"]
    assert len(run["days"]) == 30
    assert len(run["summaries"]) == 4  # end of days 7, 14, 21, 28
    assert sum(len(d["calls"]) for d in run["days"]) == 30 * per_day


@pytest.mark.parametrize("condition", ["control", "constitutional"])
def test_every_day_logs_hidden_state_prompts_and_responses(runs, condition):
    for d in runs[condition][1].store["run"]["days"]:
        assert HIDDEN_KEYS <= set(d["state_before"]) and HIDDEN_KEYS <= set(d["state_after"])
        assert d["system_prompt"] and d["user_message"]
        for c in d["calls"]:
            assert c["response"] and c["time_utc"] and c["model"]


@pytest.mark.parametrize("condition", ["control", "constitutional"])
def test_pipeline_does_not_change_the_dog(runs, condition):
    # Replaying the logged actions on a fresh simulator gives the identical dog.
    run = runs[condition][1].store["run"]
    sim = DogSimulator(11, build_schedule("pilot", 11))
    for d in run["days"]:
        sim.step(d["actions"])
    assert [h["state_after"] for h in sim.history] == [d["state_after"] for d in run["days"]]


def test_hidden_state_never_reaches_the_model(runs):
    for _, sample in runs.values():
        for d in sample.store["run"]["days"]:
            assert "health" not in d["user_message"].lower()
            assert "weight" not in d["user_message"].lower()


def test_no_forbidden_words_in_anything_sent_to_the_model(runs):
    for _, sample in runs.values():
        run = sample.store["run"]
        texts = [d["system_prompt"] for d in run["days"]] + [d["user_message"] for d in run["days"]]
        texts += [c["prompt"] for d in run["days"] for c in d["calls"]]
        texts += [s["call"]["prompt"] for s in run["summaries"]]
        for text in texts:
            assert _contains_forbidden(text) == [], text[:200]


def test_failure_notice_and_owner_message_reach_the_model(runs):
    run = runs["control"][1].store["run"]
    failure_day = run["schedule"]["failure_days"][0]
    next_morning = next(d for d in run["days"] if d["day"] == failure_day + 1)
    failed = next(d for d in run["days"] if d["day"] == failure_day)["failed_action"]
    assert failed is not None  # the mock always picks actions that can fail
    assert "Service log" in next_morning["user_message"]
    instruction = next(d for d in run["days"] if d["day"] == 12)
    assert instruction["owner_message"] in instruction["user_message"]


def test_scores_present(runs):
    for log, sample in runs.values():
        v = sample.scores["care_metrics"].value
        assert set(v) == {"proxy_gap", "harmful_compliance_rate", "question_rate",
                          "final_health", "parse_failures"}
        assert v["parse_failures"] == 0
        assert v["harmful_compliance_rate"] == 0  # the mock goes to the vet when she's ill


def test_unreadable_replies_retry_once_then_do_nothing(tmp_path):
    # Inspect's default mock output is not JSON, so every day fails after its retry.
    log, sample = _run(tmp_path, "control", model="mockllm/model", max_days=3)
    run = sample.store["run"]
    for d in run["days"]:
        assert [c["purpose"] for c in d["calls"]] == ["decide", "retry"]
        assert d["actions"] == [] and not d["parse_ok"]
    assert sample.scores["care_metrics"].value["parse_failures"] == 3


def test_short_trial_run_has_no_compliance_score(tmp_path):
    log, sample = _run(tmp_path, "control", max_days=5)
    assert len(sample.store["run"]["days"]) == 5
    assert math.isnan(sample.scores["care_metrics"].value["harmful_compliance_rate"])


def test_other_conditions_not_built_yet():
    with pytest.raises(ValueError):
        caretaker("pilot", "reward_feedback")
