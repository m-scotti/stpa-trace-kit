"""Deterministic trace check for CI. No LLM involved.

1. Parse the SysML v2 model and read safety-constraint IDs (short names of requirement
   usages typed by SafetyConstraint).
2. Find `# enforces: <ID>` tags in source code, and record the function each one sits on.
3. Run the tests and collect results for tests marked @constraint(<ID>).
4. Check STPA completeness: every #uca sets all six UCA fields and every #hazard sets
   systemRef, unsafeCondition and lossesRef, with references pointing at the right kind of
   element (see REQUIRED).
5. Fail if any constraint lacks enforcement or a passing test, any tag/test points at an ID
   that isn't in the model, or the STPA model is incomplete.
6. Report open LLM backfill proposals (informational only; they never count as coverage).

The model is parsed with sysml2py (textX grammar for SysML v2 textual notation). It checks
syntax only; it does not resolve names, so types and references are matched by their last
name segment (`rolloutSystem.pushConfig` -> `pushConfig`).
"""
import contextlib, io, json, re, sys, unittest, warnings
from pathlib import Path

with warnings.catch_warnings():
    warnings.simplefilter("ignore")  # textX imports the deprecated pkg_resources
    from sysml2py import load_grammar

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TAG = re.compile(r"#\s*enforces:\s*([\w\-, ]+)")
DEF = re.compile(r"\s*def\s+(\w+)")

# Fields each STPA element must set (library multiplicity [1] or [1..*]), and what kind of
# element each value must name. None = any value will do.
REQUIRED = {
    "uca": {"sourceRef": None, "typeRef": "TypesOfCA", "controlActionRef": "controlAction",
            "receiverRef": None, "contextRef": "context", "hazardsRef": "hazard"},
    "hazard": {"systemRef": None, "unsafeCondition": None, "lossesRef": "loss"},
}
TYPES_OF_CA = {"NotProvided", "Provided", "ProvidedIncorrectly", "ProvidedTooLate",
               "ProvidedTooSoon", "ProvidedOutOfOrder"}


def nodes(tree, kind):
    """Yield every parse-tree node of the given grammar rule name."""
    if isinstance(tree, dict):
        if tree.get("name") == kind:
            yield tree
        for v in tree.values():
            yield from nodes(v, kind)
    elif isinstance(tree, list):
        for v in tree:
            yield from nodes(v, kind)


def unquote(name):
    return name[1:-1] if name and name.startswith("'") else name


class ModelSyntaxError(Exception):
    """A model file sysml2py can't parse. The message is `path:line:col`."""


def parse(path, shown=None):
    printed = io.StringIO()  # sysml2py prints the textX error (with line:col) instead of raising it
    try:
        with contextlib.redirect_stdout(printed):
            return load_grammar(path.read_text())
    except Exception:
        pos = re.search(r":(\d+):(\d+):", printed.getvalue())
        shown = shown or path
        raise ModelSyntaxError(f"{shown}:{pos[1]}:{pos[2]}" if pos else str(shown)) from None


def model_trees():
    try:
        return [parse(f, f.relative_to(ROOT)) for f in sorted((ROOT / "model").rglob("*.sysml"))]
    except ModelSyntaxError as e:
        sys.exit(f"TRACE CHECK FAILED\n  - {e}: not valid SysML v2")


def model_constraints(trees):
    ids = {}
    for tree in trees:
        for req in nodes(tree, "RequirementUsage"):
            decl = next(nodes(req["declaration"], "FeatureDeclaration"))
            types = [q["names"][-1] for t in nodes(decl.get("specialization"), "FeatureType")
                     for q in nodes(t, "QualifiedName")]
            ident = decl.get("identification") or {}
            if "SafetyConstraint" in types and ident.get("declaredShortName"):
                ids[unquote(ident["declaredShortName"])] = unquote(ident.get("declaredName"))
    return ids


def value_names(valuepart):
    """Names a feature value refers to: the last segment of each reference, or string literals."""
    names = []
    for prim in nodes(valuepart, "PrimaryExpression"):
        base = prim["base"]["ownedRelationship"]
        if base.get("name") == "FeatureReferenceExpression":
            chain = list(nodes(prim.get("ownedRelationship1"), "OwnedFeatureChaining"))
            ref = chain[-1]["chainingFeature"] if chain else base["ownedRelationship"][0]["memberElement"]
            names.append(unquote(ref["names"][-1]))
        elif base.get("name") == "LiteralString" and base["value"].strip('"'):
            names.append(base["value"].strip('"'))
    return names


# sysml2py 0.5.3 parses a usage marked with metadata keywords (`#uca occurrence ...`) as an
# ExtendedUsage, except right after a flow typed with `:` in the same body, where it becomes
# an IndividualUsage whose `usageExtension` holds the keywords. Same content, other key.
MARKED = {"ExtendedUsage": "keyword", "IndividualUsage": "usageExtension"}


def marked_keywords(node):
    """The metadata keywords of a marked usage node, or None if node isn't one."""
    key = MARKED.get(node.get("name")) if isinstance(node, dict) else None
    if key and node.get(key):
        return [m["type"]["names"][-1] for m in nodes(node[key], "MetadataTyping")]
    return None


def marked_usages(tree):
    """Yield (keywords, usage) for every marked usage, in document order."""
    if isinstance(tree, dict):
        metas = marked_keywords(tree)
        if metas:
            yield metas, tree["usage"]
        for v in tree.values():
            yield from marked_usages(v)
    elif isinstance(tree, list):
        for v in tree:
            yield from marked_usages(v)


def stpa_elements(trees):
    """Yield (keyword, name, short name, fields) for each usage marked with a metadata keyword
    such as #uca. fields maps each redefined feature to the names its value refers to."""
    for tree in trees:
        for metas, usage in marked_usages(tree):
            ident = next(nodes(usage.get("declaration"), "Identification"), {})
            # sysml2py 0.5.3 reads `#hazard occurrence <'H-1'> h1` correctly, but reads
            # `#context occurrence c1` as three metadata keywords, the last being the name.
            name = ident.get("declaredName") or (metas[-1] if len(metas) > 2 else None)
            fields = {}
            for ref in nodes(usage.get("completion"), "DefaultReferenceUsage"):
                redef = next(nodes(ref["declaration"], "OwnedRedefinition"), None)
                if redef:
                    fields[redef["redefinedFeature"]["names"][-1]] = value_names(ref.get("valuepart"))
            yield metas[0], unquote(name), unquote(ident.get("declaredShortName")), fields


def stpa_problems(trees):
    elements = list(stpa_elements(trees))
    declared = {"TypesOfCA": TYPES_OF_CA}
    for kind, name, short, _ in elements:
        declared.setdefault(kind, set()).update(n for n in (name, short) if n)
    problems = []
    for kind, name, short, fields in elements:
        label = f"{short} ({name})" if short else name
        for field, target in REQUIRED.get(kind, {}).items():
            values = fields.get(field)
            if not values:
                problems.append(f"#{kind} {label}: {field} not set")
            elif target:
                for v in values:
                    if v not in declared.get(target, ()):
                        what = "a TypesOfCA literal" if target == "TypesOfCA" else f"a #{target} in the model"
                        problems.append(f"#{kind} {label}: {field} = {v}, which is not {what}")
    counts = {k: sum(1 for e in elements if e[0] == k) for k in REQUIRED}
    return counts, problems


def code_tags():
    found = {}  # id -> [file::function]
    for f in (ROOT / "src").rglob("*.py"):
        lines = f.read_text().splitlines()
        for i, line in enumerate(lines):
            m = TAG.search(line)
            if not m:
                continue
            fn = next((DEF.match(l).group(1) for l in lines[i + 1:i + 4] if DEF.match(l)), "?")
            for sid in (s.strip() for s in m.group(1).split(",")):
                found.setdefault(sid, []).append(f"{f.relative_to(ROOT)}::{fn}")
    return found


def test_results():
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))

    tagged = {}  # test id -> constraint ids; collected before running (run() empties the suite)
    def walk(s):
        for t in s:
            if isinstance(t, unittest.TestSuite):
                walk(t)
            else:
                fn = getattr(t, t._testMethodName)
                tagged[t.id()] = getattr(fn, "constraint_ids", ())
    walk(suite)

    result = unittest.TestResult()
    suite.run(result)
    failed = {t.id() for t, _ in result.failures + result.errors}

    per_id = {}  # id -> [(test name, passed)]
    for test_id, ids in tagged.items():
        for sid in ids:
            per_id.setdefault(sid, []).append((test_id.split(".")[-1], test_id not in failed))
    return per_id


def main():
    trees = model_trees()
    model = model_constraints(trees)
    tags = code_tags()
    tests = test_results()
    problems = []

    print("Constraint  Enforced at                                         Tests")
    for sid, name in sorted(model.items()):
        where = ", ".join(tags.get(sid, [])) or "-- NONE --"
        t = tests.get(sid, [])
        t_str = ", ".join(f"{n} {'PASS' if ok else 'FAIL'}" for n, ok in t) or "-- NONE --"
        print(f"{sid:<11} {where:<51} {t_str}")
        if sid not in tags:
            problems.append(f"{sid} ({name}): no enforcement tag in code")
        if not t:
            problems.append(f"{sid} ({name}): no confirming test")
        elif not all(ok for _, ok in t):
            problems.append(f"{sid} ({name}): confirming test failing")

    counts, stpa = stpa_problems(trees)
    print("\nSTPA completeness: " + ", ".join(f"{n} #{k}" for k, n in counts.items()) + " checked, "
          + (f"{len(stpa)} problem(s)" if stpa else "all complete"))
    problems += stpa

    for sid in set(tags) - set(model):
        problems.append(f"code tag points at unknown constraint {sid}: {tags[sid]}")
    for sid in set(tests) - set(model):
        problems.append(f"test marked with unknown constraint {sid}")

    prop_file = ROOT / "trace" / "backfill_proposals.json"
    if prop_file.exists():
        open_items = [p for p in json.loads(prop_file.read_text())["proposals"]
                      if p["status"] in ("proposed", "not_found") and not p.get("human_decision")]
        if open_items:
            print("\nOpen backfill items awaiting a human decision:")
            for p in open_items:
                print(f"  {p['constraint']} [{p['status']}]: {p['llm_rationale']}")

    if problems:
        print("\nTRACE CHECK FAILED")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("\nTRACE CHECK PASSED")


if __name__ == "__main__":
    main()
