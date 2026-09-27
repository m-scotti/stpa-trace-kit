"""Tests for control_structure.py. Run from trace-example/:
    .venv/bin/python -m unittest discover -s tools
"""
import unittest
import xml.etree.ElementTree as ET

import control_structure as cs
from trace_check import load_grammar

MODEL = """package M {
    #controlStructure part cs {
        #controller part ctrl;
        #controller part box {
            #sensor part mon;
        }
        #process part proc;
        #controlAction flow push { end ::> ctrl; end ::> proc; }
        #feedback flow health { end ::> box.mon; end ::> ctrl; }
        #feedback flow ghost { end ::> nowhere; end ::> ctrl; }
        flow status : Feedback { end ::> proc; end ::> ctrl; }
        #controlAction flow broken { end ::> ctrl; }
    }
}"""


def structure():
    return cs.read_structure([load_grammar(MODEL)])


class ReadStructure(unittest.TestCase):
    def test_parts_flows_and_warnings(self):
        title, parts, flows, warnings = structure()
        self.assertEqual(title, "cs")
        # `box` only groups `mon` and has no flows, so it is left out; `mon` names it instead.
        self.assertEqual(parts, {"ctrl": {"kind": "controller", "within": ""},
                                 "mon": {"kind": "sensor", "within": "box"},
                                 "proc": {"kind": "process", "within": ""},
                                 "nowhere": {"kind": "undeclared", "within": ""}})
        self.assertEqual([(f["name"], f["src"], f["dst"]) for f in flows],
                         [("push", "ctrl", "proc"), ("health", "mon", "ctrl"), ("ghost", "nowhere", "ctrl"),
                          ("status", "proc", "ctrl")])
        self.assertEqual(flows[-1]["kind"], "feedback")  # typed `: Feedback`, no keyword
        self.assertEqual(warnings, ["control action broken: needs exactly two ends, found 1; skipped",
                                    "feedback ghost: end nowhere is not a marked STPA part"])

    def test_stpa_rows(self):
        _, parts, flows, _ = structure()
        level = cs.levels(parts, flows)
        # Controller on top, sensor under the controller it feeds, process at the bottom.
        self.assertEqual((level["ctrl"], level["mon"], level["proc"]), (0, 1, 2))


class MergeParallel(unittest.TestCase):
    def test_same_kind_and_ends_share_one_arrow(self):
        flows = [{"kind": "control action", "name": "push", "src": "c", "dst": "p"},
                 {"kind": "control action", "name": "rollback", "src": "c", "dst": "p"},
                 {"kind": "feedback", "name": "health", "src": "p", "dst": "c"}]
        merged = cs.merge_parallel(flows)
        self.assertEqual([(f["kind"], f["name"]) for f in merged],
                         [("control action", "push\nrollback"), ("feedback", "health")])
        self.assertEqual(flows[0]["name"], "push")  # input left untouched
        parts = {"c": {"kind": "controller", "within": ""}, "p": {"kind": "process", "within": ""}}
        self.assertIn('n_c -->|"push<br/>rollback"| n_p', cs.mermaid("t", parts, flows))
        self.assertIn('n_c -> n_p: "push\\nrollback"', cs.d2("t", parts, flows))
        self.assertEqual(cs.render("t", parts, flows).count('class="edge"'), 2)  # 1 arrow + legend


class Outputs(unittest.TestCase):
    def test_svg_is_well_formed_and_names_everything(self):
        title, parts, flows, _ = structure()
        svg = cs.render(title, parts, flows)
        ET.fromstring(svg)  # raises if not well-formed XML
        for name in ("ctrl", "mon", "proc", "push", "health", "in box"):
            self.assertIn(name, svg)

    def test_d2_keeps_controllers_on_top(self):
        title, parts, flows, _ = structure()
        src = cs.d2(title, parts, flows)
        self.assertIn("layout-engine: elk", src)
        self.assertIn('n_ctrl -> n_proc: "push" {class: control-action}', src)
        # Upward feedback is written from the upper box, arrowhead at the controller.
        self.assertIn('n_ctrl <- n_mon: "health" {class: feedback}', src)
        self.assertIn("n_mon -> n_proc: pin {class: pin}", src)  # holds proc below the sensor row

    def test_mermaid_uses_elk_model_order(self):
        title, parts, flows, _ = structure()
        src = cs.mermaid(title, parts, flows)
        self.assertIn("layout: elk", src)
        self.assertIn("cycleBreakingStrategy: MODEL_ORDER", src)
        self.assertIn("nodePlacementStrategy: NETWORK_SIMPLEX", src)
        self.assertIn("considerModelOrder: NODES_AND_EDGES", src)
        self.assertLess(src.index('n_mon -.->'), src.index('n_ctrl -->'))  # feedback declared first
        # Boxes declared top-down: MODEL_ORDER relies on this to keep controllers on top.
        self.assertLess(src.index("n_ctrl["), src.index("n_mon["))
        self.assertLess(src.index("n_mon["), src.index("n_proc["))
        # Feedback keeps its real direction and arrowhead.
        self.assertIn('n_mon -.->|"health"| n_ctrl', src)
        # Invisible counter-link for Mermaid 11, whose ELK ignores MODEL_ORDER.
        self.assertIn("n_ctrl ~~~ n_mon", src)
        self.assertIn("n_mon ~~~ n_proc", src)


if __name__ == "__main__":
    unittest.main()
