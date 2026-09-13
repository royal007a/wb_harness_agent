"""Evaluate the deterministic, no-model execution-control contract fixture."""
import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.execution_control import choose_exit, evaluate_try, propagate_reliability, transition_replan


CONTRACT = json.loads((ROOT / "specs/v1/execution-control.schema.json").read_text())


def validate_fixture(value):
    schema = {"$ref": "#/$defs/evaluation_fixture", "$defs": CONTRACT["$defs"]}
    errors = list(Draft202012Validator(schema).iter_errors(value))
    if errors:
        locations = ", ".join("/".join(str(part) for part in error.path) or "$" for error in errors[:3])
        raise ValueError("invalid execution-control fixture at {}".format(locations))
    ids = [case["id"] for case in value["cases"]]
    if len(ids) != len(set(ids)):
        raise ValueError("fixture contains duplicate case IDs")


def evaluate(fixture):
    validate_fixture(fixture)
    results = []
    for case in fixture["cases"]:
        if case["kind"] == "exit":
            actual = choose_exit(case["input"])
            expected = case["expected"]
            passed = actual["exit"] == expected["exit"] and actual["chosen_action_id"] == expected["chosen_action_id"]
        elif case["kind"] == "propagation":
            actual = propagate_reliability(case["input"])
            expected = case["expected"]
            passed = actual == expected
        elif case["kind"] == "try":
            actual = evaluate_try(case["input"])
            expected = case["expected"]
            passed = actual == expected
        else:
            actual = {"status": transition_replan(case["input"]["status"], case["input"]["event"])}
            expected = case["expected"]
            passed = actual == expected
        results.append({"case_id": case["id"], "passed": passed})
    return {
        "evaluation_version": fixture["fixture_version"],
        "classification": fixture["classification"],
        "case_count": len(results),
        "passed_case_ids": [result["case_id"] for result in results if result["passed"]],
        "failed_case_ids": [result["case_id"] for result in results if not result["passed"]],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = evaluate(json.loads(args.fixture.read_text()))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print("execution-control evaluation error: {}".format(error), file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"case_count": report["case_count"], "failed_case_count": len(report["failed_case_ids"])}, ensure_ascii=False))
    return 1 if report["failed_case_ids"] else 0


if __name__ == "__main__":
    sys.exit(main())
