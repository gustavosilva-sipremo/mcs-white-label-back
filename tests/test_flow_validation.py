import unittest

from app.services.flow_validation import (
    build_blocks_index,
    validate_flow_graph_structure,
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


class TestFlowGraphStructure(unittest.TestCase):
    def test_valid_linear_graph(self):
        graph = {
            "nodes": [
                _node("s", "start", "Início"),
                _node("t", "trigger", "T1", {"mode": "preset", "branchKey": "b"}),
                _node("e", "end", "Fim"),
            ],
            "edges": [
                {"id": "1", "source": "s", "target": "t"},
                {"id": "2", "source": "t", "target": "e"},
            ],
        }
        sid, eid, logic = validate_flow_graph_structure(graph)
        self.assertEqual(sid, "s")
        self.assertEqual(eid, "e")
        self.assertEqual(len(logic), 1)
        idx = build_blocks_index(graph, sid, eid, logic)
        self.assertEqual(idx["startNodeId"], "s")
        self.assertEqual(idx["endNodeId"], "e")

    def test_two_starts_raises(self):
        graph = {
            "nodes": [
                _node("s1", "start"),
                _node("s2", "start"),
                _node("e", "end"),
            ],
            "edges": [],
        }
        with self.assertRaisesRegex(ValueError, "exactly one Start"):
            validate_flow_graph_structure(graph)

    def test_unreachable_end_raises(self):
        graph = {
            "nodes": [
                _node("s", "start"),
                _node("t", "trigger", "T", {"mode": "preset"}),
                _node("e", "end"),
            ],
            "edges": [{"id": "1", "source": "s", "target": "t"}],
        }
        with self.assertRaisesRegex(ValueError, "not reachable from Start"):
            validate_flow_graph_structure(graph)

    def test_orphan_raises(self):
        graph = {
            "nodes": [
                _node("s", "start"),
                _node("t", "trigger", "T", {"mode": "preset"}),
                _node("o", "action", "orphan", {}),
                _node("e", "end"),
            ],
            "edges": [
                {"id": "1", "source": "s", "target": "t"},
                {"id": "2", "source": "t", "target": "e"},
            ],
        }
        with self.assertRaisesRegex(ValueError, "Orphan node"):
            validate_flow_graph_structure(graph)


if __name__ == "__main__":
    unittest.main()
