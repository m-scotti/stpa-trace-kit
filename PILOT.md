# Pilot plan

Goal: find out whether this approach works on a real system. That means: can a real control
structure be encoded with the DLR library, how good are the LLM's backfill proposals, and
does the check catch real gaps?

## Before you start

- Run the reference example first (see `README.md`). It must fail on SC-3 only. If it
  fails in any other way, fix the setup before going further.
- Check the language of the code under test. The check only finds tags in Python and only
  runs unittest tests. For another language, adapt `code_tags()` and `test_results()` in
  `trace_check.py` first, and write down that you did.

## Steps

1. **Pick one real control structure** with 3–5 safety constraints. Choose one where you
   already know, or can find out, where each constraint is enforced. Without that you
   can't judge the LLM's answers. If possible, include at least one constraint you suspect
   is not enforced.

2. **Encode it with the library.** Make a copy of `trace-example/` and replace
   `model/rollout_safety.sysml`, using it and `SysMLv2LibrarySTPA/Library/ExampleSTPA.sysml`
   as patterns. You need losses, hazards, the control structure (controllers, processes,
   sensors, control actions, feedback), contexts, and one UCA per constraint. Write the
   constraints as `requirement <'SC-n'> name : SafetyConstraint`, each pointing at the UCA it
   inverts. The Syside Problems panel must be clean, and the check's completeness line
   must say "all complete". Note how long this takes and where the library gets in the way.

3. **Run the backfill.** Give an LLM the prompt in `BACKFILL_PROMPT.md`, the model file and
   the source code, and save its output as `trace/backfill_proposals.json`. Remove all
   `# enforces:` tags from the code first, so the LLM can't simply copy them.

4. **Judge every proposal** without looking at the LLM's reasoning first. Open the proposed
   location, or for `not_found`, search the code yourself. Then assign one verdict per
   constraint in the table below:
   - **correct location**: the LLM proposed a location, and that code enforces the constraint.
   - **wrong location**: the LLM proposed a location that doesn't enforce the constraint,
     whether or not enforcement exists elsewhere. Say which in the notes.
   - **real gap**: the LLM found nothing, and the constraint really is not enforced.
   - **missed enforcement**: the LLM found nothing, but enforcement exists. Note where.

   Record your decision in the JSON too: set `human_decision` on every entry
   (e.g. `"confirmed"`, `"rejected: enforced in X::y instead"`, `"gap accepted"`).

5. **Tag and test the confirmed ones.** For each enforced constraint, place
   `# enforces: SC-n` above the enforcing function yourself, and write or mark at least one
   test with `@constraint("SC-n")` that would fail if enforcement were removed. Real gaps get
   no tag. They stay as failures, or are fixed in the code and then tagged and tested.

6. **Run the check.** It should fail exactly on the real gaps and pass everything else. Any
   other failure is a finding: a model problem, a tag or test problem, or a limit of the check.

## Scoring table

| Constraint | LLM result | My verdict | Notes |
|---|---|---|---|
| SC-1 | | | |
| SC-2 | | | |
| SC-3 | | | |
| SC-4 | | | |
| SC-5 | | | |

- **LLM result:** `proposed: file::function` or `not_found`.
- **My verdict:** correct location / wrong location / real gap / missed enforcement.

## Summary to record after the pilot

- Proposals judged correct location or real gap, out of the total.
- Wrong locations and missed enforcements: what the LLM got wrong, and whether its
  "searched" list would have shown you why.
- Time spent on modelling, judging and tagging.
- Library or Syside problems (see `trace-example/HANDOFF.md` for the ones already known).
- False alarms or missed problems from the check itself.
