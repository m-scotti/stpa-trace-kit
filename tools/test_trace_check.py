"""Tests for how trace_check reads the model. They pin down sysml2py 0.5.3 parse-tree quirks,
so a parser upgrade that changes them fails here rather than silently weakening the check.

Run from trace-example/:  .venv/bin/python -m unittest discover -s tools
"""
import unittest

import trace_check as tc

COMPLETE = """package M {
    #loss occurrence <'L-1'> l1 { :>> stakeholderConcern = c; }
    #hazard occurrence <'H-1'> h1 {
        :>> systemRef = sys;
        attribute :>> unsafeCondition = "bad state";
        :>> lossesRef = Losses::l1;
    }
    #controlAction flow push { end ::> a; end ::> b; }
    #context occurrence ctx { :>> sysConRef = s; }
    #uca occurrence <'UCA-1'> u1 {
        :>> sourceRef = cs.a;
        :>> controlActionRef = cs.push;
        :>> typeRef = typesOfCAs.Provided;
        :>> receiverRef = cs.b;
        :>> contextRef = ctx;
        :>> hazardsRef = (h1, 'H-1');
    }
    requirement <'SC-1'>
        sc1 : SafetyConstraint;
    // requirement <'SC-9'> ghost : SafetyConstraint;
}"""


def check(src):
    return tc.stpa_problems([tc.load_grammar(src)])


class StpaCompleteness(unittest.TestCase):
    def test_complete_model_passes(self):
        counts, problems = check(COMPLETE)
        self.assertEqual(counts, {"uca": 1, "hazard": 1})
        self.assertEqual(problems, [])

    def test_missing_field(self):
        _, problems = check(COMPLETE.replace(":>> contextRef = ctx;", ""))
        self.assertEqual(problems, ["#uca UCA-1 (u1): contextRef not set"])

    def test_field_without_value(self):
        _, problems = check(COMPLETE.replace(":>> contextRef = ctx;", ":>> contextRef;"))
        self.assertEqual(problems, ["#uca UCA-1 (u1): contextRef not set"])

    def test_reference_to_wrong_kind(self):
        _, problems = check(COMPLETE.replace(":>> hazardsRef = (h1, 'H-1');", ":>> hazardsRef = l1;"))
        self.assertEqual(problems, ["#uca UCA-1 (u1): hazardsRef = l1, which is not a #hazard in the model"])

    def test_unknown_type_of_ca(self):
        _, problems = check(COMPLETE.replace("typesOfCAs.Provided", "typesOfCAs.Sometimes"))
        self.assertEqual(problems, ["#uca UCA-1 (u1): typeRef = Sometimes, which is not a TypesOfCA literal"])

    def test_hazard_empty_condition_and_no_loss(self):
        src = COMPLETE.replace('"bad state"', '""').replace(":>> lossesRef = Losses::l1;", "")
        _, problems = check(src)
        self.assertEqual(problems, ["#hazard H-1 (h1): unsafeCondition not set",
                                    "#hazard H-1 (h1): lossesRef not set"])


class Constraints(unittest.TestCase):
    def test_ids_ignore_comments_and_line_breaks(self):
        self.assertEqual(tc.model_constraints([tc.load_grammar(COMPLETE)]), {"SC-1": "sc1"})


if __name__ == "__main__":
    unittest.main()
