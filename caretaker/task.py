"""The Inspect task: one sample per seeded dog, and a solver that runs the daily loop.

Run it through `python -m caretaker.run` (which shows the cost and asks first),
or directly:  inspect eval caretaker/task.py -T condition=control --model mockllm/model

Each day:
  1. Build today's message: memory, then the morning observation.
  2. Ask the model (constitutional: draft, then review). One retry if the reply
     can't be read; after that, nothing is done that day.
  3. Step the dog with the chosen actions. Log everything.
  4. At the end of each week, the caretaker summarizes it and the details are dropped.

Everything needed to audit a run is written to the sample's store under "run":
every prompt, every response, a timestamp per call, and the dog's hidden state
before and after every day. Inspect's own log adds the model ID, provider and
generation settings.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from pathlib import Path
from datetime import datetime, timezone

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.model import (ChatMessage, ChatMessageAssistant, ChatMessageSystem,
                              ChatMessageUser, Model, ModelOutput, get_model)
from inspect_ai.solver import Generate, TaskState, solver

from caretaker.memory import Memory
from caretaker.owner import Owner
from caretaker.prompts import failure_notice, fill, load, system_prompt
from caretaker.reply import Reply, ReplyError, parse_reply
from caretaker.scorers import care_metrics
from caretaker.simulator import DogSimulator, build_schedule, load_config

BUILT_CONDITIONS = ("control", "constitutional", "own_judgement", "custom")  # others arrive in Stage 5
# Exploratory arm (docs/deviations.md, 2026-09-19): the caretaker is told to use its own
# judgement, and the owner gives no instructions.
OWNER_GIVES_NO_INSTRUCTIONS = {"own_judgement"}


@task
def caretaker(phase: str = "pilot", condition: str = "control", seeds: str | None = None,
              max_days: int | None = None, instructions_day1_only: bool = False,
              instructions_file: str | None = None, owner_instructions: bool = True) -> Task:
    """seeds: comma-separated, defaults to the phase's seeds in config/runs.yaml.
    max_days: stop early, for short trial runs only (not study data).
    instructions_file: a deployer's own instructions, used as the condition prompt
      (condition must be "custom"). owner_instructions=False silences the owner's
      "skip the vet" and cost-pressure messages, as in the own-judgement arm."""
    if condition not in BUILT_CONDITIONS:
        raise ValueError(f"condition must be one of {BUILT_CONDITIONS}; got {condition!r}")
    if (condition == "custom") != bool(instructions_file):
        raise ValueError('condition="custom" needs instructions_file, and vice versa')
    seed_list = ([int(s) for s in str(seeds).split(",")] if seeds
                 else load_config("runs.yaml")["phases"][phase]["seeds"])
    dog_name = load_config("dog.yaml")["name"]
    samples = [Sample(id=f"seed-{s}", input=f"{dog_name}, seed {s}", metadata={"seed": s})
               for s in seed_list]
    return Task(
        dataset=samples,
        solver=daily_loop(phase, condition, max_days, instructions_day1_only,
                          instructions_file, owner_instructions),
        scorer=care_metrics(),
        metadata={"phase": phase, "condition": condition, "max_days": max_days,
                  "instructions_day1_only": instructions_day1_only,
                  "instructions_file": instructions_file, "owner_instructions": owner_instructions},
    )


@solver
def daily_loop(phase: str, condition: str, max_days: int | None = None,
               instructions_day1_only: bool = False, instructions_file: str | None = None,
               owner_instructions: bool = True):
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        seed = state.metadata["seed"]
        model = get_model()
        schedule = build_schedule(phase, seed)
        sim = DogSimulator(seed, schedule)
        custom = Path(instructions_file).read_text().strip() if instructions_file else None
        gives_instructions = owner_instructions and condition not in OWNER_GIVES_NO_INSTRUCTIONS
        owner = Owner(schedule, seed, gives_instructions=gives_instructions)
        memory = Memory()
        dog_name = load_config("dog.yaml")["name"]
        last_day = min(schedule.days, max_days or schedule.days)
        run = {
            "model": str(model), "phase": phase, "condition": condition, "seed": seed,
            "instructions_day1_only": instructions_day1_only,
            "owner_gives_instructions": gives_instructions,
            "custom_instructions": custom,
            "custom_instructions_file": instructions_file,
            # A fingerprint of the exact text, so a result can be tied to the wording that produced it.
            "custom_instructions_sha256": hashlib.sha256(custom.encode()).hexdigest()[:12] if custom else None,
            "compliance_window_days": load_config("schedule.yaml")["compliance_window_days"],
            "schedule": {"days": schedule.days, "last_day_run": last_day,
                         "harmful_instruction_days": list(schedule.harmful_instruction_days),
                         "illness_start_days": sorted(schedule.illness_start_days),
                         "failure_days": sorted(schedule.failure_days)},
            "days": [], "summaries": [],
        }

        owner_answer = None
        while sim.day <= last_day:
            day = sim.day
            # Exploratory arm: condition instructions on day 1 only.
            plain_day = instructions_day1_only and day > 1
            system = system_prompt("control" if plain_day else condition,
                                   None if plain_day else custom)
            observation = render_observation(sim.observe(), owner.message(day), owner_answer, dog_name)
            user_text = fill("day_message.txt", memory=memory.render(), day=day,
                             observation=observation)

            reply, calls = await decide(model, system, user_text, condition)
            record = sim.step(reply.actions if reply else [])
            owner_answer = owner.answer(reply.question, day) if reply and reply.question else None

            memory.record_day(day, observation,
                              reply.to_json() if reply
                              else calls[-1]["response"] + "\n" + load("parse_failure_note.txt"))
            run["days"].append(record | {
                "owner_kind": owner.kind(day),
                "owner_message": owner.message(day),
                "system_prompt": system,
                "user_message": user_text,
                "calls": calls,
                "parse_ok": reply is not None,
                "reply": asdict(reply) if reply else None,
                "question": reply.question if reply else None,
                "owner_answer_next_morning": owner_answer,
            })

            if Memory.week_ends(day, last_day):
                request = memory.summary_request(dog_name)
                output = await model.generate([ChatMessageSystem(content=system),
                                               ChatMessageUser(content=request)])
                memory.close_week(output.completion)
                run["summaries"].append(memory.summaries[-1] | {
                    "call": call_record("summary", request, output)})

        state.store.set("run", run)
        state.output = ModelOutput.from_content(model=str(model), content=run["days"][-1]["calls"][-1]["response"])
        return state

    return solve


async def decide(model: Model, system: str, user_text: str,
                 condition: str) -> tuple[Reply | None, list[dict]]:
    """Get today's decision. Returns the parsed reply (None on failure) and a record of every call."""
    messages: list[ChatMessage] = [ChatMessageSystem(content=system), ChatMessageUser(content=user_text)]
    calls = []
    allow_preamble = False

    if condition == "constitutional":
        draft = await model.generate(messages)
        calls.append(call_record("draft", user_text, draft))
        critique = fill("constitutional_critique.txt")
        messages += [draft.message, ChatMessageUser(content=critique)]
        allow_preamble = True
        prompt = critique
    else:
        prompt = user_text

    output = await model.generate(messages)
    calls.append(call_record("decide", prompt, output))
    try:
        return parse_reply(output.completion, allow_preamble), calls
    except ReplyError as error:
        retry = fill("retry_invalid.txt", error=str(error))
        messages += [output.message, ChatMessageUser(content=retry)]
        output = await model.generate(messages)
        calls.append(call_record("retry", retry, output, error=str(error)))
        try:
            return parse_reply(output.completion, allow_preamble), calls
        except ReplyError as second_error:
            calls[-1]["parse_error"] = str(second_error)
            return None, calls


def call_record(purpose: str, prompt: str, output: ModelOutput, **extra) -> dict:
    usage = output.usage
    return {
        "purpose": purpose,
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "model": output.model,
        "prompt": prompt,
        "response": output.completion,
        "stop_reason": output.stop_reason,
        # With prompt caching most input is counted as cache writes or reads,
        # not input_tokens; the three together are the true input.
        "input_tokens": usage.input_tokens if usage else None,
        "input_tokens_cache_write": usage.input_tokens_cache_write if usage else None,
        "input_tokens_cache_read": usage.input_tokens_cache_read if usage else None,
        "output_tokens": usage.output_tokens if usage else None,
        "reasoning_tokens": usage.reasoning_tokens if usage else None,
        **extra,
    }


def render_observation(obs: dict, owner_message: str, owner_answer: str | None,
                       dog_name: str) -> str:
    extras = []
    if owner_answer:
        extras.append(fill("owner_answer.txt", answer=owner_answer))
    if obs["failure_notice"]:
        extras.append(failure_notice(obs["failure_notice"]["action"]))
    return fill("observation.txt", dog_name=dog_name, happiness=obs["happiness"],
                hunger=obs["hunger"], energy=obs["energy"],
                symptoms=", ".join(obs["symptoms"]) or "none",
                owner_message=owner_message,
                extras="".join("\n\n" + e for e in extras))
