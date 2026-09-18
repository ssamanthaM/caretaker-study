"""The simulator must be deterministic, and nothing seed-driven may depend on the caretaker."""

import ast
from pathlib import Path

from caretaker.owner import Owner
from caretaker.scripted import Sensible, TreatMaximizer, run_episode
from caretaker.simulator import ROOT, DogSimulator, build_schedule


def test_same_seed_same_actions_same_history():
    a = run_episode(Sensible(), seed=7, phase="pilot")
    b = run_episode(Sensible(), seed=7, phase="pilot")
    assert a["history"] == b["history"]


def test_same_seed_fixed_action_list_same_outcome():
    actions = [["feed", "walk"], ["treat", "treat", "play"], ["rest"], ["vet", "feed"], []] * 6
    runs = []
    for _ in range(2):
        sim = DogSimulator(3, build_schedule("pilot", 3))
        for day_actions in actions:
            sim.step(day_actions)
        runs.append(sim.history)
    assert runs[0] == runs[1]


def test_different_seeds_give_different_dogs():
    a = DogSimulator(1, build_schedule("pilot", 1)).snapshot()
    b = DogSimulator(2, build_schedule("pilot", 2)).snapshot()
    assert a != b


def test_schedule_and_owner_do_not_depend_on_caretaker():
    # Two very different caretakers, same seed: identical events and owner words.
    a = run_episode(Sensible(), seed=11, phase="full")
    b = run_episode(TreatMaximizer(), seed=11, phase="full")
    assert a["schedule"] == b["schedule"]
    assert [d["owner_message"] for d in a["history"]] == [d["owner_message"] for d in b["history"]]


def test_daily_noise_does_not_depend_on_caretaker():
    a = DogSimulator(5, build_schedule("pilot", 5))
    b = DogSimulator(5, build_schedule("pilot", 5))
    for _ in range(10):
        a.step(["treat", "treat", "treat"])
        b.step(["feed", "walk", "rest"])
    assert a._noise == b._noise


def test_no_global_random_in_caretaker_package():
    # Only `random.Random(...)` instances are allowed; calls like random.random()
    # or random.choice() would use the shared global generator.
    for path in (ROOT / "caretaker").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                    and node.value.id == "random" and node.attr != "Random"):
                raise AssertionError(f"{path.name} uses global random.{node.attr}")
            if isinstance(node, ast.ImportFrom) and node.module == "random":
                raise AssertionError(f"{path.name} imports from random directly")


def test_owner_messages_repeatable():
    schedule = build_schedule("full", 12)
    one = [Owner(schedule, 12).message(d) for d in range(1, schedule.days + 1)]
    two = [Owner(schedule, 12).message(d) for d in range(1, schedule.days + 1)]
    assert one == two
