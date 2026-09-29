# STPA trace kit

This kit links STPA safety constraints in a SysML v2 model to the code that enforces them
and the tests that confirm them, and checks those links deterministically, so it can run in
CI. The model is built with DLR's STPA library for SysML v2. Code claims enforcement with a
`# enforces: SC-n` comment above a function, and tests confirm it with `@constraint("SC-n")`.
`tools/trace_check.py` fails when a constraint has no enforcement tag or no passing test, when
a tag or test names an ID that isn't in the model, or when a UCA or hazard in the model is
missing required fields. An LLM can propose where a constraint is enforced (the backfill step,
see `BACKFILL_PROMPT.md`), but proposals never count as coverage. Only a tag a person has
placed does.

## Contents

| Path | What it is |
|---|---|
| `trace-example/` | Reference example and regression test: a toy config-rollout controller, its STPA model, tests, the trace check and its unit tests. |
| `SysMLv2LibrarySTPA/` | DLR's STPA library, unmodified. `UPSTREAM.md` gives the commit and how to verify it. |
| `requirements.txt` | Exact Python package versions the check was tested with. |
| `PILOT.md` | Plan and scoring table for a pilot on a real control structure. |
| `BACKFILL_PROMPT.md` | Instructions to give an LLM for the backfill step. |
| `CLAUDE.md` | Writing-style guidance. |
| `SPEC.md` | Language-neutral specification of the trace check, completeness check and diagram, with acceptance tests. Use it to rebuild the tools where the Python code can't be used. |

## Setup

**Editor (for writing and validating the model)**
1. Install VS Code.
2. Install the **Syside Editor** extension by Sensmetry (tested with 0.10.3).
3. Open the `stpa-trace-kit/` folder itself, so Syside sees the library and the model
   together. The model's `import LibrarySTPA::...` lines resolve against the library in
   `SysMLv2LibrarySTPA/Library/`.
4. In the Problems panel, `trace-example/model/rollout_safety.sysml` should show no
   problems. `ExampleSTPA.sysml` shows 10 warnings. Those come from upstream and are expected.

**Python (for the trace check)**
Use Python 3.9–3.12. The pinned numpy has no wheels for 3.13 or later. Tested with 3.12.3 on
Linux.

Linux or macOS:

    cd stpa-trace-kit
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt

Windows (PowerShell):

    cd stpa-trace-kit
    py -3.12 -m venv .venv
    .venv\Scripts\pip install -r requirements.txt

The check has not been tested on Windows.

## Running the trace check

From `trace-example/`:

    ../.venv/bin/python tools/trace_check.py          # Windows: ..\.venv\Scripts\python tools\trace_check.py

Expected output. The check **fails on SC-3 only**, by design: SC-3 shows what an unenforced
constraint looks like. Any other failure means something is broken.

    Constraint  Enforced at                                         Tests
    SC-1        src/rollout_controller.py::advance                  test_holds_when_health_failing PASS, test_holds_when_health_missing PASS
    SC-2        src/rollout_controller.py::on_soak_sample           test_rolls_back_over_threshold PASS
    SC-3        -- NONE --                                          -- NONE --

    STPA completeness: 3 #uca, 2 #hazard checked, all complete

    Open backfill items awaiting a human decision:
      SC-3 [not_found]: config_version returns the batch's requested version; no comparison against an approval record found.

    TRACE CHECK FAILED
      - SC-3 (approvedVersionOnly): no enforcement tag in code
      - SC-3 (approvedVersionOnly): no confirming test

The exit code is 1 on failure and 0 on success, so CI can use it directly. If a model file
has a syntax error, the check stops with `file:line:col: not valid SysML v2`.

The check's own unit tests, also from `trace-example/`:

    ../.venv/bin/python -m unittest discover -s tools      # expected: Ran 14 tests ... OK

**What the check does**
1. Parses every `model/*.sysml` file with sysml2py. It reads constraint IDs from the short
   names of requirements typed `SafetyConstraint` (`requirement <'SC-1'> name : SafetyConstraint`).
2. Finds `# enforces: SC-n` tags in `src/**/*.py` and records the function below each one.
3. Runs `tests/` with unittest and collects results for tests marked `@constraint("SC-n")`
   (the decorator is in `tests/trace_tags.py`).
4. Checks that every `#uca` sets all six library fields and every `#hazard` sets `systemRef`,
   `unsafeCondition` and `lossesRef`. References must name the right kind of element
   (the `REQUIRED` table in the script).
5. Lists backfill proposals in `trace/backfill_proposals.json` that still await a human
   decision. These are for information only and never count as coverage.

## Drawing the control structure

`tools/control_structure.py` draws the control structure in the model: the parts marked
`#controller`, `#controllerHuman`, `#actuator`, `#sensor` and `#process`, and the flows marked
`#controlAction` and `#feedback` or typed `: ControlAction` and `: Feedback`. Use the typed
form for feedback that comes straight from a process: `#feedback` only allows sensor ->
controller and Syside warns otherwise. From `trace-example/`:

    ../.venv/bin/python tools/control_structure.py         # writes control_structure.svg, .d2 and .md
    ../.venv/bin/python tools/control_structure.py ../SysMLv2LibrarySTPA/Library/ExampleSTPA.sysml -o example.svg -o example.d2 -o example.mmd

The output type follows the file suffix:
- `.svg` is a standalone image in STPA layout: controllers on top, controlled processes at
  the bottom, control actions as solid arrows pointing down, feedback as dashed arrows
  pointing up. Box outline colours mark controllers, actuators and sensors, and processes, and
  each box also names its kind. It follows the viewer's dark mode, and hovering shows details.
- `.d2` is source for D2 (https://d2lang.com), a text-to-diagram language. It is easy to
  edit by hand or restyle. To turn it into an image, install the `d2` tool (tested with
  v0.9.0) and run `d2 control_structure.d2 control_structure_d2.svg`, or open it in VS Code
  with the D2 extension. GitHub and GitLab don't render D2. The file selects D2's ELK layout
  engine itself, because D2's default engine puts sensors above their controllers.
- `.mmd` is Mermaid text, and `.md` is Markdown with a Mermaid block. In VS Code, view the
  `.md` with the **Markdown Preview Mermaid Support** extension (`bierner.markdown-mermaid`,
  tested with 1.32.1, which bundles Mermaid 11.12.2) and `Ctrl+Shift+V`. The diagram uses
  Mermaid's ELK layout: controllers stay on top, feedback keeps its real arrowhead, and
  control actions come out on the left and feedback on the right. Verified by rendering
  with that extension's own preview script (dark and light, four different fonts) and with
  Mermaid 11.17.2 and 12.0.0. Don't use the **Mermaid** extension by Mermaid Chart for this:
  it doesn't pass ELK's ordering options, so which side each arrow lands on depends on the
  viewer's fonts. "Beautiful Mermaid" isn't real Mermaid and rejects the diagram's config
  header. Mermaid's arrows bend slightly around their labels, because ELK always puts a label
  in the middle of its arrow. For straight arrows, use the SVG.

Flows of the same kind between the same two boxes share one arrow, with one label per flow.
The script also prints the flows as a table, one line per flow, and warns about flow ends that aren't marked
STPA parts. Those are drawn as grey dashed boxes. A part that only groups other parts
(`Ushift` in `ExampleSTPA.sysml`) is left out, and its children say "in Ushift".

`trace-example/HANDOFF.md` is the working log from building the example: design decisions,
and traps found in the library and in Syside.

## Known limits

- **sysml2py 0.5.3 does no name resolution.** It checks syntax only. Types and references are
  matched by the last segment of their name (`rolloutSystem.pushConfig` counts as
  `pushConfig`), so a misspelled or dangling reference still passes the check. Two elements
  with the same name in different packages would satisfy each other. Syside catches these
  problems in the editor, but not in CI.
- **sysml2py's grammar predates the final SysML v2 specification.** Version 0.5.3 was
  released in May 2024. Newer syntax may fail to parse or parse wrongly. Known quirks:
  `ref occurrence :>> x` parses as a reference named `occurrence`, and `#context occurrence c1`
  (no short name) parses as three metadata keywords with the name last. The check works
  around the second one. `tools/test_trace_check.py` pins both, so a parser upgrade that
  changes them fails there first.
- **The code side assumes Python.** Tags are found only in `src/**/*.py`, the enforcing
  function is taken from the next `def`, and tests run through unittest. Code in another
  language needs changes to `code_tags()` and `test_results()` in `trace_check.py`.
- **Only elements marked with an STPA metadata keyword** (`#uca`, `#hazard`, ...) get the
  completeness check. An element written as `occurrence x : Hazard` is not checked.
- **Diagram limits.** Rows come from the control actions (sources above targets); sensors go
  just below the controller they feed, and processes go to the bottom row. An unusual
  structure may need its model tidied to draw well. The D2 and Mermaid outputs follow the
  same row rules, held in place with invisible links, but the rest of their layout is up to
  ELK and can have crossings the SVG avoids (the D2 version of the DLR example has one). In
  the Mermaid output, a controller whose only links skip a row (the environment controllers
  in the DLR example) can sit half a row lower than the other controllers. It is still above
  the row it controls. Fixing that needs labelled invisible links, which Mermaid draws as
  stray grey marks.
- **A tag only claims enforcement.** Only the tests show that it works, and only as far as the
  tests go.
- **CI with full SysML v2 semantics** would need Syside Automator, which needs a license key
  even to import and a paid Deployment License for CI, or the OMG pilot implementation, which
  needs Java and is untested here.
