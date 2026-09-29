# Backfill prompt

Give the text below to the LLM, together with the SysML v2 model file(s) and the source code
(or access to the repository). Save its output as `trace/backfill_proposals.json`.

---

You are helping trace safety constraints from an STPA analysis to the code that enforces them.
Your output is a set of **proposals** for a person to review. It does not count as evidence
of enforcement.

## Rules

- **Do not edit any file.** Do not add `# enforces:` tags, do not add or change tests, and do
  not fix code, even if you find a gap. A person places every tag after reviewing your proposals.
- Only report what you found in the code you were given. Do not guess where code "probably"
  is, and do not assume enforcement happens in code you cannot see.
- A location only counts if the code there actually prevents the unsafe behaviour. For
  example, it checks the condition and refuses, stops, or corrects. A comment, log line,
  or variable name that mentions the constraint is not enforcement.

## Input

The safety constraints are requirements in the SysML v2 model, written as
`requirement <'SC-n'> name : SafetyConstraint`. Each has a `doc` comment stating the
constraint and an `inverts` reference to the unsafe control action (UCA) it prevents. Use the
UCA's control action, context and hazard to understand what the code must prevent.

## What to do for each constraint

1. State in your own words what the code must do or must never do.
2. Search the code for where that behaviour is decided. Look for the control action being
   issued, and for the conditions that allow or block it.
3. If you find code that enforces it, propose that location. If enforcement is spread over
   several functions, give one entry per function and say in each rationale how they combine.
4. If you find nothing, report `not_found` and list what you searched.

## Output

Output only a JSON document in exactly this format. Include every constraint in the model,
in ID order:

```json
{
  "_note": "LLM backfill output. Proposals do NOT count toward coverage; only in-code tags do. A human confirms by placing the tag, or adjudicates not_found.",
  "proposals": [
    {"constraint": "SC-1", "status": "proposed",
     "location": "src/rollout_controller.py::RolloutController.advance",
     "llm_rationale": "Returns without pushing when the current batch's health report is missing or unhealthy, so a push never happens without healthy feedback.",
     "searched": "Callers of push(): only advance. Checked the guard at the top of advance.",
     "human_decision": null},
    {"constraint": "SC-3", "status": "not_found",
     "location": null,
     "llm_rationale": "config_version returns the batch's requested version unchanged; nothing compares it to an approved version.",
     "searched": "Every function in src/rollout_controller.py; searched all of src/ for 'approv', 'version', 'allowlist'. No approval record exists in the code.",
     "human_decision": null}
  ]
}
```

Field rules:
- `constraint`: the short ID from the model, e.g. `"SC-1"`.
- `status`: `"proposed"` if you found an enforcing location, `"not_found"` if not. Never use
  any other value. In particular, never use `"confirmed"`: only a person can confirm.
- `location`: `"path/to/file.py::function"` with the path relative to the repository root,
  or `"path/to/file.py::Class.method"` for methods. Use `null` when `not_found`.
- `llm_rationale`: your reasoning. Say what the code does, and why that does or doesn't
  enforce the constraint. Refer to specific conditions, calls or values.
- `searched`: what you looked at and where: files, functions, search terms, call paths.
  Required for `not_found`, so the reviewer can tell a real gap from a search you didn't make.
  For `proposed`, give it briefly.
- `human_decision`: always `null`. The reviewer fills it in.
