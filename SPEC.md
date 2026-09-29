# Specification: trace check, completeness check, diagram

This describes the tools in `trace-example/tools/` precisely enough to rebuild them in any
language, without the Python code. Build the trace check first: it is the part the pilot
depends on. The completeness check is useful but optional, and the diagram is optional.
Section 5 lists input/expected-output pairs to check a rebuild against.

Terms: STPA is System-Theoretic Process Analysis. A UCA (unsafe control action) is a control
action that is hazardous in a given context. A safety constraint (SC) is a requirement that
prevents a UCA. "Model" means the SysML v2 textual model files.

## 1. Inputs and conventions

The check runs from a repository root with these locations (make them configurable):

| Input | Location in the example | Content |
|---|---|---|
| Model | `model/*.sysml` | SysML v2 text, built on the DLR STPA library |
| Code | `src/` | The code that enforces constraints |
| Tests | `tests/` | Tests, some marked with the constraint they confirm |
| Backfill proposals | `trace/backfill_proposals.json` | LLM proposals, optional (format in `BACKFILL_PROMPT.md`) |

**Safety constraints in the model.** Each constraint is a requirement usage with a short name
(the ID) and a name, typed by `SafetyConstraint`:

    requirement <'SC-1'> holdOnMissingHealth : SafetyConstraint { ... }

The ID is the short name without its quotes (`SC-1`). SysML allows the declaration to span
several lines, and the ID may be written without quotes (`<SC1>`).

**Enforcement tags in code.** A comment containing `enforces:` followed by one or more IDs
separated by commas, placed directly above the function that enforces them:

    # enforces: SC-1
    # enforces: SC-4, SC-5

Use the code's own comment syntax (`//` in Java or C#). The tag belongs to the first function
definition found within the next 3 lines. If there is none, record the function as `?`.

**Test markers.** A test is marked with the IDs it confirms. The example uses a Python
decorator, `@constraint("SC-1")`. Use whatever your test framework offers: an annotation, an
attribute, a tag or a naming convention. A test may confirm several IDs.

## 2. Trace check

### 2.1 Steps

1. **Read constraint IDs** from every model file (2.2). Result: a map from ID to name.
2. **Find tags** in every code file (section 1). Result: a map from ID to a list of
   `path::function`, with `path` relative to the repository root.
3. **Run the tests** and record, for each marked test, pass or fail. A test counts as failed
   if it fails or errors. Result: a map from ID to a list of (test name, passed), one entry
   per marked test (a test marked with two IDs appears under both). The example lists tests
   in the order the framework discovers them (alphabetical); order is not significant.
4. **Collect problems**, in this order:
   1. For each constraint ID in the model, sorted by ID:
      - no tag: `<ID> (<name>): no enforcement tag in code`
      - no marked test: `<ID> (<name>): no confirming test`
      - at least one marked test failed: `<ID> (<name>): confirming test failing`
   2. Completeness problems (section 3), if that check is built.
   3. For each tag ID not in the model: `code tag points at unknown constraint <ID>: [<locations>]`
   4. For each test-marker ID not in the model: `test marked with unknown constraint <ID>`
5. **Report open backfill items** (2.4).
6. **Print the result and exit** (2.3).

Proposals never count as coverage. Only tags and tests do.

### 2.2 Reading constraint IDs

A constraint is found only in model text that SysML would parse, not in comments.

- **With a SysML v2 parser:** take every requirement usage whose type's last name segment is
  `SafetyConstraint` and that has a short name. The Python version uses sysml2py 0.5.3, which
  checks syntax only and doesn't resolve names.
- **Without a parser (acceptable for a pilot):**
  1. Remove comments: `//` to end of line, and `/* ... */` blocks. This also removes `doc`
     comment text, which is harmless here.
  2. Match `requirement <'ID'> name : SafetyConstraint` with any whitespace, including line
     breaks, between the parts, and with or without quotes around the ID. As a regular
     expression: `requirement\s*<'?([^'>]+)'?>\s*(\w+)\s*:\s*SafetyConstraint`.

  This doesn't check syntax, so a model with syntax errors still yields IDs. Syside (the
  SysML editor) catches syntax errors while you edit.

If a parser is used and a file doesn't parse, stop, print
`TRACE CHECK FAILED` and `  - <file>:<line>:<col>: not valid SysML v2`, and exit with 1.

### 2.3 Output and exit code

A table, one row per constraint, sorted by ID, then any sections that apply, then the verdict:

    Constraint  Enforced at                                         Tests
    SC-1        src/rollout_controller.py::advance                  test_holds_when_health_failing PASS, test_holds_when_health_missing PASS
    SC-3        -- NONE --                                          -- NONE --

    STPA completeness: 3 #uca, 2 #hazard checked, all complete

    Open backfill items awaiting a human decision:
      SC-3 [not_found]: <llm_rationale>

    TRACE CHECK FAILED
      - SC-3 (approvedVersionOnly): no enforcement tag in code

- Table columns: ID padded to 11 characters, locations joined by `, ` and padded to 51,
  tests as `<name> PASS|FAIL` joined by `, `. An empty cell is `-- NONE --`. Exact column
  widths don't matter for correctness.
- Completeness line: `STPA completeness: <n> #uca, <m> #hazard checked, ` followed by
  `all complete` or `<k> problem(s)`.
- Verdict: if there are problems, `TRACE CHECK FAILED` and one `  - <problem>` line each, exit
  code 1. Otherwise `TRACE CHECK PASSED`, exit code 0. CI uses the exit code.

### 2.4 Backfill proposals

If the file exists, list every proposal whose `status` is `proposed` or `not_found` and whose
`human_decision` is missing, null or empty, as `  <constraint> [<status>]: <llm_rationale>`
under `Open backfill items awaiting a human decision:`. This is informational only: it never
adds a problem and never changes the exit code. Ignore unknown fields such as `searched`.

## 3. Completeness check (optional)

Syside checks that references have the right type, but not that required fields are filled in.
This check does.

### 3.1 What it reads

- **Marked elements:** usages written with a metadata keyword, such as
  `#uca occurrence <'UCA-1'> u1 { ... }`. The keyword is the word right after `#`. Each has a
  name (`u1`) and optionally a short name (`UCA-1`, quotes removed). Keywords used: `uca`,
  `hazard`, `loss`, `controlAction`, `context`.
- **Fields:** inside the element's body, each line of the form `:>> field = value;` or
  `attribute :>> field = value;`. A field written without a value (`:>> field;`) counts as
  not set.
- **Values:** a list of names, taken from the value as follows:
  - a reference gives its last name segment: `rolloutSystem.pushConfig` gives `pushConfig`,
    `Losses::l1` gives `l1`, `'H-1'` gives `H-1`;
  - a list `(a, b)` gives each item;
  - a string literal gives its text, and an empty string `""` gives nothing.

### 3.2 Rules

Required fields, and what kind of element each value must name ("any" means any value):

| Element | Field | Must name |
|---|---|---|
| `#uca` | `sourceRef` | any |
| `#uca` | `typeRef` | a TypesOfCA literal |
| `#uca` | `controlActionRef` | a `#controlAction` |
| `#uca` | `receiverRef` | any |
| `#uca` | `contextRef` | a `#context` |
| `#uca` | `hazardsRef` | a `#hazard` |
| `#hazard` | `systemRef` | any |
| `#hazard` | `unsafeCondition` | any (text) |
| `#hazard` | `lossesRef` | a `#loss` |

The TypesOfCA literals are `NotProvided`, `Provided`, `ProvidedIncorrectly`,
`ProvidedTooLate`, `ProvidedTooSoon`, `ProvidedOutOfOrder`.

"Names a `#hazard`" means the value equals the name or short name of some element marked
`#hazard` anywhere in the model. There is no real name resolution: two elements with the same
name in different packages would satisfy each other.

For each element, with `<label>` being `<short name> (<name>)`, or just `<name>` without a
short name:

- field missing or without value: `#<keyword> <label>: <field> not set`
- a value that doesn't name the required kind:
  `#<keyword> <label>: <field> = <value>, which is not a #<kind> in the model`, or for
  `typeRef`: `#uca <label>: typeRef = <value>, which is not a TypesOfCA literal`

Check fields in the table's order, and elements in model order.

### 3.3 Parser traps found with sysml2py 0.5.3

If you use sysml2py, or write your own reader, test these. Each one silently lost elements or
names at some point:
- `#context occurrence c1 {` (no short name) is read as three metadata keywords, the last one
  being the name.
- Inside a part body, a `#keyword` usage that follows a flow typed with `:`
  (`flow fb : Feedback { ... }`) parses as a different grammar rule (`IndividualUsage`) than
  usual (`ExtendedUsage`). A reader that only looks for one form skips that element without
  any warning.
- `ref occurrence :>> inverts = x;` is read as a reference *named* `occurrence`.
- References by quoted short name (`'H-1'`) keep their quotes unless removed.

## 4. Diagram (optional)

Draws the control structure. The simplest useful rebuild writes Mermaid text (4.4) for the
"Markdown Preview Mermaid Support" VS Code extension. Syside Modeler can also draw diagrams if
you have a license.

### 4.1 What it reads

- **Boxes:** parts marked `#controller`, `#controllerHuman` (shown as "human controller"),
  `#actuator`, `#sensor`, `#process`. A box nested inside another marked part records that
  container (`in Ushift`). A container with no flows of its own is left out, and its
  children say `· in <container>` under their kind.
- **Arrows:** flows marked `#controlAction` or `#feedback`, or typed `: ControlAction` or
  `: Feedback`, each with exactly two ends, `end ::> source;` then `end ::> target;`. An end
  is matched to a box by its last name segment (`box.mon` gives `mon`).
- **Warnings** (to stderr, drawing continues):
  - a flow without exactly two ends is skipped:
    `<kind> <name>: needs exactly two ends, found <n>; skipped`
  - an end that isn't a marked box becomes a grey dashed box:
    `<kind> <name>: end <end> is not a marked STPA part`
- **Merging:** flows of the same kind, source and target become one arrow whose label lists
  each flow on its own line, in model order.

### 4.2 Rows

1. Controllers (including human controllers) that receive no control action go in row 0.
2. Following control actions, each target goes one row below its source, taking the longest
   path. Stop after as many passes as there are boxes, which ends control-action cycles.
3. A feedback source that has no row yet goes one row below the box it feeds.
4. Any box still without a row goes in row 0.
5. Processes go at least one row below every box that isn't a process.

Control actions then point down, and feedback points up whenever its target is higher.

### 4.3 SVG (the Python version's own layout)

The goals, as implemented: control actions as solid arrows and feedback as dashed arrows; box
outline colour by kind (controllers blue `#2a78d6`, actuators and sensors orange `#eb6834`,
processes green `#1baf7a`, undeclared grey dashed); each box states its kind in text; straight
vertical lines with right-angled steps where needed; labels beside the line (actions left,
feedback right); boxes centred over their lines and widened to meet them; a legend listing
only the kinds and line styles present. The layout itself is a layered graph layout with
waypoints; any method that meets the goals is fine.

### 4.4 Mermaid

Required, or the rows and sides come out wrong:

    ---
    config:
      theme: base
      themeVariables:
        primaryColor: "#fcfcfb"
        primaryTextColor: "#0b0b0b"
        lineColor: "#52514e"
        edgeLabelBackground: "#fcfcfb"
      layout: elk
      elk:
        cycleBreakingStrategy: MODEL_ORDER
        nodePlacementStrategy: NETWORK_SIMPLEX
        considerModelOrder: NODES_AND_EDGES
    ---
    flowchart TB

- Declare boxes sorted by row, top row first (model order within a row), as
  `n_<id>["<b>name</b><br/>kind"]`, where `<id>` is the name with non-word characters
  replaced by `_`.
- Declare all feedback arrows before all control actions: `n_a -.->|"label"| n_b` for
  feedback and `n_a -->|"label"| n_b` for control actions, always in the flow's real
  direction. Stacked labels use `<br/>`.
- For each feedback arrow that points up, add an invisible link from its target down to its
  source: `n_upper ~~~ n_lower`. Mermaid 11 needs this to keep controllers on top.
- Pin boxes to their rows: for each box without a link to the row directly above, add
  `n_<first box of that row> ~~~ n_<box>`; for each box without a link to the row directly
  below, add `n_<box> ~~~ n_<first box of that row>`. Don't repeat links.
- No `title:` in the header: it renders dark-on-dark in dark previews. Put a Markdown heading
  above the diagram instead.

Known limits: arrows bend slightly around their labels, because ELK centres labels on their
arrows. The "Mermaid" extension by Mermaid Chart ignores the ordering settings, so its sides
depend on the viewer's fonts.

### 4.5 D2

Same rules with D2 syntax: `vars: { d2-config: { layout-engine: elk } }` (D2's default engine
puts sensors above controllers), upward feedback written from the upper box
(`n_ctrl <- n_sensor: "label"`), invisible pin links with `style.opacity: 0` and a label (ELK
gives labels their own row, so unlabelled pins let boxes drift), and link labels at 12 px.

## 5. Acceptance tests

### 5.1 The example repository

Model `trace-example/model/rollout_safety.sysml`, code `src/rollout_controller.py`, tests
`tests/test_rollout_controller.py` (all in the kit, or rebuild them from these descriptions):
- `advance` is tagged SC-1, and two tests marked SC-1 pass.
- `on_soak_sample` is tagged SC-2, and one test marked SC-2 passes.
- SC-3 has no tag and no test.

Expected: the output shown in `README.md` ("Running the trace check"), exit code 1, with
exactly two problems, both for SC-3.

### 5.2 Trace check cases

Start from the example each time and change one thing:

| Change | Expected |
|---|---|
| Add `// requirement <'SC-9'> ghost : SafetyConstraint;` to the model | SC-9 does not appear |
| Split SC-2's declaration over three lines | SC-2 still found, unchanged result |
| Remove the `;` after `inverts = pushUnapproved` (parser versions only) | `model/rollout_safety.sysml:154:5: not valid SysML v2`, exit 1 |
| Tag a function `enforces: SC-7` | problem `code tag points at unknown constraint SC-7: [...]` |
| Mark a test with SC-8 | problem `test marked with unknown constraint SC-8` |
| Make SC-2's test fail | problem `SC-2 (rollbackOnErrors): confirming test failing` |
| Tag and test SC-3 | `TRACE CHECK PASSED`, exit 0 |
| Set `human_decision` on the SC-3 proposal | no "Open backfill items" section |

### 5.3 Completeness cases

Base model (complete, no problems; counts `1 #uca, 1 #hazard`):

    package M {
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
    }

Constraint IDs read from it: exactly `SC-1` (name `sc1`).

| Change to the base | Expected problems |
|---|---|
| Delete `:>> contextRef = ctx;` | `#uca UCA-1 (u1): contextRef not set` |
| Replace it with `:>> contextRef;` | `#uca UCA-1 (u1): contextRef not set` |
| `:>> hazardsRef = l1;` | `#uca UCA-1 (u1): hazardsRef = l1, which is not a #hazard in the model` |
| `typesOfCAs.Sometimes` | `#uca UCA-1 (u1): typeRef = Sometimes, which is not a TypesOfCA literal` |
| `unsafeCondition = ""` and no `lossesRef` | `#hazard H-1 (h1): unsafeCondition not set`, then `#hazard H-1 (h1): lossesRef not set` |

Element after a typed flow (the second parser trap in 3.3) must still be checked:

    package M {
        #loss occurrence <'L-1'> l1;
        part grp {
            flow fb : Feedback { end ::> a; end ::> b; }
            #hazard occurrence <'H-2'> h2 { :>> systemRef = s; }
        }
    }

Expected: 1 hazard checked, problems `#hazard H-2 (h2): unsafeCondition not set` and
`#hazard H-2 (h2): lossesRef not set`.

DLR's `ExampleSTPA.sysml` (unmodified, commit `cde7d6a`): counts `1 #uca, 2 #hazard`, and
exactly these problems:

    #hazard VehicleCanNotExecuteMission: systemRef not set
    #hazard VehicleCanNotExecuteMission: unsafeCondition not set
    #hazard VehicleTooCloseToPeople: systemRef not set
    #hazard VehicleTooCloseToPeople: unsafeCondition not set

The example repository's model: `3 #uca, 2 #hazard`, no problems.

### 5.4 Diagram cases

    package M {
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
    }

Expected:
- Boxes: `ctrl` (controller), `mon` (sensor, in `box`), `proc` (process), `nowhere`
  (undeclared). `box` is left out.
- Arrows: push ctrl→proc, health mon→ctrl, ghost nowhere→ctrl, status proc→ctrl (a
  feedback, although it has no keyword).
- Warnings, in order: `control action broken: needs exactly two ends, found 1; skipped`,
  then `feedback ghost: end nowhere is not a marked STPA part`.
- Rows: ctrl 0, mon 1, proc 2.

Example repository: rows `rolloutController` 0 and `batch` 1; two arrows, a control action
labelled `pushConfig` / `rollback` and a feedback labelled `healthReport` / `errorRate`.

DLR example: row 0 Teleoperator, Passenger, OtherTraffic, VRUs, Environment; row 1
ControlElectronics; row 2 PerceptionSystem, DriveSystem; row 3 VehicleMovement. No warnings.
In a correct Mermaid render, each control action is left of the feedback between the same
two boxes, and DriveSystem is left of PerceptionSystem.
