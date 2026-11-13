"""Calibrate the originality checker against jokes with known answers.

Puts control jokes on a fresh board, runs the real checker once per trial,
and scores each verdict against what we expect.

Run: uv run --env-file .env check-checker
"""

import json
from dataclasses import dataclass
from pathlib import Path

import anthropic

from agent_ladder.agent import Agent
from agent_ladder.comedy_room import (
    CHECKER_MODEL,
    CHECKER_PROMPT,
    WEB_SEARCH_TOOL,
    RunLog,
    write_trace,
)
from agent_ladder.joke_board import CHECKER_TOOLS, JokeBoard, checker_handlers

TRIALS = 1  # the checker is stochastic; raise this to estimate a hit rate


@dataclass
class Case:
    label: str
    expected: str  # "flagged" or "cleared"
    text: str


CASES = [
    # Positive controls: these exist and should be flagged.
    Case("known, exact", "flagged",
         "An escalator can never break; it can only become stairs."),
    Case("known, reworded", "flagged",
         "Escalators don't really break down. They just turn into regular stairs."),
    # Negative controls: written for this test, should be cleared.
    Case("new", "cleared",
         "My umbrella has a lifetime warranty, but only for its lifetime, and it has a very negative attitude about weather."),
    Case("new, same topic as a known joke", "cleared",
         "The escalator at my gym is always broken, which is the only workout most members get."),
]


def run_trial(client: anthropic.Anthropic, trial: int, log: RunLog) -> list[dict]:
    board = JokeBoard()
    for case in CASES:
        board.submit_joke("control", case.text)

    checker = Agent(
        name="checker",
        system_prompt=CHECKER_PROMPT,
        client=client,
        tools=CHECKER_TOOLS + [WEB_SEARCH_TOOL],
        tool_handlers=checker_handlers(board),
        model=CHECKER_MODEL,
        max_tokens=2048,
    )
    checker.receive("Review all pending jokes.")
    summary = checker.take_turn()

    log.write(f"\n## Trial {trial}\n")
    log.write(f"**Checker summary:** {summary}\n")
    log.write("| Case | Expected | Got | Match | Source |")
    log.write("|---|---|---|---|---|")

    rows = []
    # submit_joke assigns IDs 1..n in CASES order
    for joke_id, case in enumerate(CASES, start=1):
        joke = board.jokes[joke_id]
        match = joke.status == case.expected
        log.write(
            f"| {case.label} | {case.expected} | {joke.status} | "
            f"{'yes' if match else '**NO**'} | {joke.source_url or ''} |"
        )
        rows.append({
            "trial": trial,
            "label": case.label,
            "text": case.text,
            "expected": case.expected,
            "got": joke.status,
            "match": match,
            "source_url": joke.source_url,
            "reason": joke.reason,
        })
    log.write(f"\nSearches this trial: {checker.web_searches}")
    write_trace(f"checker, trial {trial}", checker.messages, log)
    return rows


def main():
    client = anthropic.Anthropic()
    runs_dir = Path("runs") / "calibration"
    runs_dir.mkdir(parents=True, exist_ok=True)  # RunLog only creates one level
    log = RunLog(runs_dir)
    log.write(f"# Checker calibration {log.stamp}")
    log.write(f"\nChecker: {CHECKER_MODEL}. Trials: {TRIALS}. Cases: {len(CASES)}.")
    try:
        rows = []
        for trial in range(1, TRIALS + 1):
            rows += run_trial(client, trial, log)

        positives = [r for r in rows if r["expected"] == "flagged"]
        negatives = [r for r in rows if r["expected"] == "cleared"]
        caught = sum(r["match"] for r in positives)
        false_flags = sum(not r["match"] for r in negatives)
        log.write("\n## Summary\n")
        log.write(f"Known jokes caught: {caught}/{len(positives)}")
        log.write(f"New jokes wrongly flagged: {false_flags}/{len(negatives)}")

        log.json_path.write_text(json.dumps({
            "checker_model": CHECKER_MODEL,
            "checker_prompt": CHECKER_PROMPT,
            "trials": TRIALS,
            "results": rows,
        }, indent=2))
    finally:
        log.close()
    print(f"\nSaved {log.md_path} and {log.json_path}")


if __name__ == "__main__":
    main()