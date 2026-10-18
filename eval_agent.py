"""Eval harness for the data analyst agent.

Usage:
    python eval_agent.py             # run every test once
    python eval_agent.py --runs 3    # run each test 3 times (LLMs are non-deterministic)

A test passes when EVERY group in `checks` has AT LEAST ONE of its alternatives
present in the agent's answer. Matching is case-insensitive and ignores commas and $.
"""
import argparse
import json
import re
import time
from pathlib import Path

CSV = str(Path(__file__).parent / "sample_sales.csv")

TESTS = [
    {"name": "row count",
     "question": "How many rows are in the dataset?",
     "checks": [["48"]]},
    {"name": "total revenue",
     "question": "What is the total revenue across the whole dataset?",
     "checks": [["2285436"]]},
    {"name": "top region by revenue",
     "question": "Which region has the highest total revenue?",
     "checks": [["north"]]},
    {"name": "most returns",
     "question": "Which region has the most returns in total, and how many?",
     "checks": [["south"], ["197"]]},
    {"name": "biggest monthly drop",
     "question": "Which month had the biggest drop in total revenue compared to the previous month, and by how much?",
     "checks": [["2025-08", "august"], ["65587"]]},
    {"name": "revenue per unit",
     "question": "Which region has the highest average revenue per unit sold (total revenue / total units)?",
     "checks": [["north"], ["122.4", "122.39"]]},
    {"name": "H1 vs H2",
     "question": "Compare total revenue in Jan-Jun versus Jul-Dec. Which half earned more, and what were the totals?",
     "checks": [["1151132"], ["1134304"]]},
    {"name": "biggest % drop Jul to Aug",
     "question": "Which region had the largest percentage drop in revenue from July to August?",
     "checks": [["south"], ["35.5"]]},
    {"name": "revenue share",
     "question": "What percentage of total revenue comes from the North region?",
     "checks": [["28.5"]]},
    {"name": "lowest East month",
     "question": "In which month was East's revenue the lowest, and what was it?",
     "checks": [["2025-08", "august"], ["26955"]]},
    {"name": "unanswerable (no cost column)",
     "question": "What was the profit margin in March?",
     "checks": [["cannot", "can't", "not possible", "no cost", "not available", "unable",
                 "does not contain", "doesn't contain", "no profit", "missing", "couldn't solve"]]},
]


def normalize(text: str) -> str:
    text = re.sub(r"[\u2010-\u2015\u2212]", "-", text)  # fancy hyphens/dashes -> "-"
    text = re.sub(r"[\u00a0\u202f\u2009]", " ", text)    # special spaces -> normal space
    return re.sub(r"[,$]", "", text.lower())


def passes(answer: str, checks: list[list[str]]) -> bool:
    ans = normalize(answer)
    return all(any(normalize(alt) in ans for alt in group) for group in checks)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args()

    from agent import run_agent, llm  # imported here so passes() can be tested without the LLM stack

    results, passed, total, retries_sum = [], 0, 0, 0
    start = time.time()

    for t in TESTS:
        t_pass = 0
        for run in range(args.runs):
            try:
                out = run_agent(t["question"], CSV)
                answer, retries = out["answer"], out.get("retries", 0)
                ok = passes(answer, t["checks"])
            except Exception as e:  # agent crash counts as a failure
                answer, retries, ok = f"CRASH: {e}", 0, False

            t_pass += ok
            passed += ok
            total += 1
            retries_sum += retries
            results.append({"test": t["name"], "run": run + 1, "pass": ok,
                            "retries": retries, "answer": answer})
            time.sleep(1)  # be gentle with free-tier rate limits

        mark = "PASS" if t_pass == args.runs else ("PART" if t_pass else "FAIL")
        print(f"[{mark}] {t['name']:<32} {t_pass}/{args.runs}")

    print("\n" + "=" * 52)
    print(f"Model:         {getattr(llm, 'model_name', 'unknown')}")
    print(f"Accuracy:      {passed}/{total} ({100 * passed / total:.0f}%)")
    print(f"Avg retries:   {retries_sum / total:.2f}")
    print(f"Time:          {time.time() - start:.0f}s")

    Path("eval_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("Details saved to eval_results.json (check failed answers there)")


if __name__ == "__main__":
    main()
