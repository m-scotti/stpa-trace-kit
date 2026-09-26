# Handoff: STPA constraint-to-code traceability in SysML v2

## Goal
Link STPA safety constraints in a SysML v2 model to the code that enforces them and the
tests that confirm them, and check that link deterministically in CI (continuous integration).
An LLM may *propose* links ("backfill"), but proposals never count as coverage. Only a
human-placed tag in the code does.

## Workspace layout (WSL)
- `SysMLv2LibrarySTPA/Library/LibrarySTPA.sysml`: DLR STPA library (local copy may have
  modifications relative to GitHub, so use this copy as the reference).
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

## Current state
`rollout_safety.sysml` is built on the DLR library (imports `DefineAnalysisPurpose`,
`ModelControlStructure`, `IdentifyUCAs`, `MetaTypesSTPA`) and passes Syside with no problems.
Elements are bound the way `ExampleSTPA.sysml` does it, with metadata keywords (`#loss`,
`#hazard`, `#controller`, `#uca`, ...), which make each element subset the matching library usage:
- Loss L-1 (`lossOfService`), tied to the `serviceAvailability` concern. Hazards H-1
  (`faultyConfigSpreads`) and H-2 (`unapprovedConfigRunning`), each with `systemRef`,
  `unsafeCondition` and `lossesRef` filled in.
- Control structure `rolloutSystem`: controller `rolloutController`, process `batch`,
  sensor `healthMonitor`; control actions `pushConfig`, `rollback` (matching `push()` /
  `rollback()` in `src/rollout_controller.py`); feedback `healthReport`, `errorRate`.
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
- Tests for the model-reading code: `.venv/bin/python -m unittest discover -s tools`.

## Lessons from the library rewrite
- Library feedback is declared `from sensors ... to controllers`, so a `#feedback` flow must
  run sensor -> controller. That is why `healthMonitor` exists, and it is also the cause of all
  10 warnings in `ExampleSTPA.sysml`. `#controlAction` has no such constraint.
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
  refreshes, focus the file in VS Code.

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
- A tag shows where enforcement is claimed; only the tests show it works.
