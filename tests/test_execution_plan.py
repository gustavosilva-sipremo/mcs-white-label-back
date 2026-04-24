import unittest

from app.services.flow_validation import (
    build_execution_plan,
    validate_execution_plan_rules,
)


def _node(nid, bt, label="x", config=None):
    data = {"blockType": bt, "label": label}
    if config is not None:
        data["config"] = config
    return {
        "id": nid,
        "type": "flowBlock",
        "position": {"x": 0, "y": 0},
        "data": data,
    }


class TestBuildExecutionPlan(unittest.TestCase):
    def test_entry_branches_and_placed_steps(self):
        logic = [
            _node("t", "trigger", "T", {"mode": "preset", "branchKey": "main"}),
            _node(
                "d",
                "data",
                "D",
                {
                    "flowBranchKey": "main",
                    "flowStepOrder": 0,
                    "formRef": {"id": "x"},
                },
            ),
            _node(
                "a",
                "action",
                "End",
                {
                    "flowBranchKey": "main",
                    "flowStepOrder": 1,
                    "kind": "finish_occurrence",
                },
            ),
        ]
        plan = build_execution_plan(logic)
        self.assertEqual(len(plan["entryBranches"]), 1)
        self.assertEqual(plan["entryBranches"][0]["branchKeys"], ["main"])
        self.assertEqual(len(plan["stepsByBranch"]["main"]), 2)
        self.assertEqual(plan["stepsByBranch"]["main"][0]["order"], 0)
        self.assertEqual(plan["stepsByBranch"]["main"][1]["order"], 1)
        self.assertEqual(len(plan["terminals"]), 1)
        validate_execution_plan_rules(logic)

    def test_duplicate_placement_raises(self):
        logic = [
            _node("t", "trigger", "T", {"mode": "preset", "branchKey": "b"}),
            _node(
                "d1",
                "data",
                "D1",
                {"flowBranchKey": "b", "flowStepOrder": 0},
            ),
            _node(
                "d2",
                "data",
                "D2",
                {"flowBranchKey": "b", "flowStepOrder": 0},
            ),
            _node(
                "a",
                "action",
                "End",
                {"flowBranchKey": "b", "flowStepOrder": 1, "kind": "finish_occurrence"},
            ),
        ]
        with self.assertRaisesRegex(ValueError, "Duplicate flow placement"):
            validate_execution_plan_rules(logic)


if __name__ == "__main__":
    unittest.main()
