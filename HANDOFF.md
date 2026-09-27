# Handoff: STPA constraint-to-code traceability in SysML v2

## Goal
Link STPA safety constraints in a SysML v2 model to the code that enforces them and the
tests that confirm them, and check that link deterministically in CI (continuous integration).
An LLM may *propose* links ("backfill"), but proposals never count as coverage. Only a
human-placed tag in the code does.

## Workspace layout (WSL)
- `SysMLv2LibrarySTPA/Library/LibrarySTPA.sysml`: DLR STPA library. The local checkout has
  no changes against GitHub (checked 2026-09-26: clean tree, `origin/main` at `cde7d6a`).
- `SysMLv2LibrarySTPA/Library/ExampleSTPA.sysml`: the library authors' worked example.
  Use it as the pattern for how library elements get bound. It currently shows 10 Syside problems.
- `SysMLv2LibrarySTPA/Library/CameoViewsSTPA.sysml`: ~285 Syside errors. Not imported by
  our model; ignore.
- `trace-example/`: the example repo. `model/rollout_safety.sysml` is our example model
  (passes Syside with no problems). Also `src/`, `tests/`, `tools/trace_check.py`,
  `trace/backfill_proposals.json`:
  a toy config-rollout controller with `# enforces: SC-n` tags, tests marked
  `@constraint("SC-n")`, and a trace check that fails CI when a constraint lacks an
  enforcement tag or a passing test. SC-3 is deliberately unenforced to show the failure.
- `stpa-trace-kit/` and `stpa-trace-kit.zip`: the package for running a pilot at work. It holds
  a copy of `trace-example/` plus the generated diagrams, an unmodified copy of the DLR library
  with `UPSTREAM.md` (commit, how to verify), a pinned `requirements.txt`, `README.md`,
  `PILOT.md`, `BACKFILL_PROMPT.md` and `CLAUDE.md`. After changing `trace-example/`, copy the
  changed files into the kit, regenerate the diagrams there, repeat the fresh-venv install
  test and rebuild the zip.

## Current state
`rollout_safety.sysml` is built on the DLR library (imports `DefineAnalysisPurpose`,
`ModelControlStructure`, `IdentifyUCAs`, `MetaTypesSTPA`) and passes Syside with no problems.
Elements are bound the way `ExampleSTPA.sysml` does it, with metadata keywords (`#loss`,
`#hazard`, `#controller`, `#uca`, ...), which make each element subset the matching library usage:
- Loss L-1 (`lossOfService`), tied to the `serviceAvailability` concern. Hazards H-1
  (`faultyConfigSpreads`) and H-2 (`unapprovedConfigRunning`), each with `systemRef`,
  `unsafeCondition` and `lossesRef` filled in.
- Control structure `rolloutSystem`: controller `rolloutController` and process `batch`;
  control actions `pushConfig`, `rollback` (matching `push()` / `rollback()` in
  `src/rollout_controller.py`); feedback `healthReport`, `errorRate` straight from the batch,
  typed `: Feedback` (see the first lesson below).
- One environmental condition (`liveTraffic`), three system conditions, and three contexts
  that pair them through `envConRef` / `sysConRef`.
- UCA-1 `pushWithoutHealth` (`Provided`), UCA-2 `noRollbackOnErrors` (`NotProvided`,
  on `rollback`), UCA-3 `pushUnapproved` (`ProvidedIncorrectly`). All six UCA fields are set.
- SC-1..SC-3 are unchanged plain requirements; `SafetyConstraint.inverts` is typed
  `UnsafeControlAction`. `.venv/bin/python tools/trace_check.py` fails only on SC-3, as intended.
- `trace_check.py` also checks STPA completeness, since Syside doesn't: every `#uca` sets all
  six fields and every `#hazard` sets `systemRef`, `unsafeCondition` and `lossesRef`. It also
  checks that `typeRef` is a `TypesOfCA` literal and that `controlActionRef` / `contextRef` /
  `hazardsRef` / `lossesRef` name a `#controlAction` / `#context` / `#hazard` / `#loss`. The rules
  are the `REQUIRED` table in the script. Run on `ExampleSTPA.sysml`, it flags exactly the two
  hazards with empty `systemRef` / `unsafeCondition`.
- `tools/control_structure.py` draws the control structure from the model as an SVG
  (`.svg`), D2 source (`.d2`), Mermaid (`.mmd`) or Markdown with a Mermaid block (`.md`),
  chosen by output suffix. With no arguments, from `trace-example/`, it writes
  `control_structure.svg`, `.d2` and `.md` for `model/*.sysml`. It reads `#controller` /
  `#controllerHuman` / `#actuator` / `#sensor` / `#process` parts, and flows marked
  `#controlAction` / `#feedback` or typed `: ControlAction` / `: Feedback`. Rows follow STPA:
  controllers on top, processes at the bottom, control actions down, feedback up. Flows of
  the same kind between the same two boxes share one arrow with stacked labels.
  - The SVG does its own layout: straight orthogonal lines, labels beside the lines (actions
    left, feedback right), boxes centred and widened to meet their lines.
  - D2 and Mermaid lay themselves out with ELK. Both keep controllers on top through
    invisible links; see the lessons below. View the Mermaid `.md` in VS Code with
    "Markdown Preview Mermaid Support" (`bierner.markdown-mermaid`).
- Tests for the tools: `.venv/bin/python -m unittest discover -s tools` (14 tests).

## Lessons from the library rewrite
- Library feedback is declared `from sensors ... to controllers`, so a `#feedback` flow must
  run sensor -> controller. That is the cause of all 10 warnings in `ExampleSTPA.sysml`.
  `#controlAction` has no such constraint. To run feedback straight from a process, type the
  flow by the library definition instead (`flow x : Feedback`): the sensor rule is on the
  library usage that `#feedback` attaches to, not on `Feedback` itself. An earlier version
  of the model had a `healthMonitor` sensor for this reason, which drew as a floating box.
- In sysml2py 0.5.3, a `#keyword` usage that follows a flow typed with `:` inside a part body
  parses as `IndividualUsage` instead of `ExtendedUsage`. Both tools handle both forms
  (`marked_usages()` in `trace_check.py`); `test_element_after_typed_flow_is_still_checked`
  guards it.
- Don't name a part after a metadata keyword (`controller`, `sensor`, `process`, `loss`,
  `hazard`, `uca`, `context`, ...). The part hides the `#keyword` inside its scope, and Syside
  reports "Metadata feature cannot be typed by an abstract metaclass".
- A `concern` needs a `subject` ("Subject must be the first input parameter").
- `ExampleSTPA.sysml` sets `systemConditions` / `environmentalConditions` in its context.
  The library's `Context` defines `sysConRef` / `envConRef`; use those.
- Syside checks that references conform to their types, but not that required (`[1]`) fields
  are filled in. The example's hazards pass with `systemRef` and `unsafeCondition` left empty.
- Syside diagnostics can be read with the IDE tool `mcp__ide__getDiagnostics`, but results lag
  edits. Check that `linesInFile` matches the file on disk and call it twice. If it never
  refreshes, focus the file in VS Code. Watch for a second editor tab holding a stale or
  garbled copy of a file: close it without saving. The kit's copy of the model and library
  in the same workspace causes a "`RolloutSafety` shadows" warning; that one is expected.

## Lessons from the diagram tool
- Mermaid has no link with an arrowhead only at its start, and D2's and Mermaid's default
  layout engine (dagre) ranks boxes by arrowhead direction, so feedback pulls sensors above
  their controllers. ELK fixes it: D2's ELK follows the direction a link is written in
  (`controller <- sensor`); Mermaid 12's ELK follows declaration order with `MODEL_ORDER`
  cycle breaking. Mermaid 11's ELK ignores that setting, so the Mermaid output also adds an
  invisible `upper ~~~ lower` link beside each upward feedback link.
- ELK gives every edge label a row of its own and always centres labels on their link, so
  Mermaid arrows bend a little around their labels. The SVG is the straight version.
- The "Mermaid" extension by Mermaid Chart doesn't pass ELK's ordering options, so which side
  an arrow lands on depends on the viewer's fonts. "Beautiful Mermaid" isn't real Mermaid and
  rejects the config header. "Markdown Preview Mermaid Support" (1.32.1, Mermaid 11.12.2)
  passes the options and was verified to put actions left and feedback right.
- To check diagrams without a GUI: render Mermaid with `@mermaid-js/mermaid-cli` or with an
  extension's own `dist-preview` bundle in headless Chrome (needs `libnss3` and `libnspr4`,
  which `apt download` + `dpkg -x` provide without sudo), and read box positions from the SVG.
  Test under several fonts: a layout that depends on text sizes can differ on another machine.

## Next task
None assigned.

## Known limits
- `trace_check.py` parses the model with `sysml2py` (textX grammar, free, pure Python).
  Setup: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` (system pip is
  blocked by PEP 668). It fails CI with `file:line:col` on a syntax error, and it ignores
  commented-out requirements. Limits:
  - Syntax only, no name resolution: `SafetyConstraint` is matched by its simple name, and a
    misspelled type or reference would pass the parser (Syside would catch it).
  - Its grammar isn't fully faithful: `ref occurrence :>> inverts` parses as a reference
    named `occurrence`, and `#context occurrence c1` (no short name) parses as three metadata
    keywords, the last being the name. `trace_check.py` works around the second one;
    `tools/test_trace_check.py` pins both, so a parser upgrade that changes them fails there.
  - Completeness references are matched by last name segment, not resolved: two elements
    with the same name in different packages would satisfy each other. Only elements marked
    with a metadata keyword (`#uca`, `#hazard`, ...) are checked, not `occurrence x : Hazard`.
  - Last release May 2024; textX imports `pkg_resources`, hence the `setuptools<81` pin.
  Alternatives with full semantics: Syside Automator (needs a license key even to import,
  plus a paid Deployment License for CI) or the OMG pilot implementation (needs a JDK; untested).
- Diagram layout: the SVG's layout is heuristic. Crowded rows can still give a line one or two
  steps, and an unusual structure may need its model tidied to draw well. D2 and Mermaid
  layouts are up to ELK beyond the row order.
- A tag shows where enforcement is claimed; only the tests show it works.
