# Engineering Review Checklist

Use this before final handoff for substantial MatchForge changes.

Any unresolved required issue returns the task to implementation or owner review.

## Scope

- Does the change implement exactly the requested/authorized scope?
- Did it add any speculative abstraction, flag, configuration, dependency, schema field, or future-phase scaffold?
- Is any unrelated cleanup mixed into the diff?
- Does every new production symbol have a current consumer or explicit contract reason?
- Is the diff the smallest complete coherent change?

## Source of truth

- Did the implementation follow the newest applicable owner/Wayfinder decision?
- Did a stale `PLAN.md` statement override a newer resolved decision?
- Are approved ADRs, policies, schemas, migrations, and persisted compatibility rules respected?
- Were unresolved conflicts surfaced rather than silently decided?

## Architecture

- Does Python still own football data/modelling?
- Does Rust remain pure deterministic simulation?
- Does Go remain serving/operations?
- Do SQL migrations remain persistence authority?
- Did dependency direction remain correct?
- Was a duplicate implementation path introduced?

## Data and identity

- Are MatchForge IDs stable?
- Are provider IDs retained as source/mapping data rather than model identity?
- Are provider observations traceable to exact sources?
- Was raw provider data kept immutable?
- Was any unknown provider value silently coerced?

## Point-in-time safety

- Are `football_cutoff`, `knowledge_cutoff`, and `knowledge_mode` preserved where required?
- Is the target outcome structurally absent from pre-match input?
- Are same-kickoff matches forecast before any same-batch outcome update?
- Can current/latest database state leak into historical reconstruction?
- Are feature lookbacks prior-only?
- Are historical corrections gated by when the data was known?

## Models and probabilities

- Did mathematical behavior change?
- If yes, was the change explicitly authorized?
- Are assumptions and numerical tolerances defined?
- Are probabilities finite, within bounds, and normalized?
- Does one coherent joint distribution drive related goal products?
- Was invalid state rejected rather than silently clipped?
- Did complexity earn its place against the approved simpler baseline?

## Artifacts and forecasts

- Are published artifacts immutable?
- Are logical and physical checksums handled according to contract?
- Does a forecast bind exact immutable artifact identities?
- Are mutable aliases resolved before persistence?
- Do reload/round-trip predictions reproduce?
- Can partial publication recover safely?

## Persistence

- Were accepted migrations left unchanged?
- Are new constraints/indexes correct?
- Is upgrade behavior tested?
- Are existing timestamps/IDs interpreted consistently?
- Is retry/idempotency behavior safe?

## Testing

- Did a focused test fail first where TDD was practical?
- Are important decision branches covered?
- Are failure paths covered?
- Are point-in-time invariants covered?
- Are artifact serialization/reload paths covered?
- Are concurrency/retry paths covered where relevant?
- Were exact verification commands actually run?

## Complexity

- What is the cyclomatic complexity of changed decision-heavy units?
- Is any unit above the configured threshold?
- If no configured threshold exists, is any materially changed unit above 10?
- Was complexity genuinely reduced rather than hidden?

## Minimality and dead code

- Did the task add helpers, wrappers, factories, interfaces, flags, or extension points for hypothetical use?
- Is any new production code justified only by a test?
- Did the implementation duplicate an existing responsibility?
- Are there unused imports, variables, private symbols, parameters, modules, configuration keys, branches, or files?
- Did caller migration make an old path obsolete?
- Are commented-out alternatives, temporary debug code, TODO/FIXME placeholders, or dormant scaffolds left behind?
- Was task-obsoleted code removed where safe and in scope?

## Documentation

- Did a durable architecture/contract/operation rule change?
- If yes, was the owning document updated?
- Was unnecessary documentation avoided?
- Is current project status left to the tracked machine-readable authority?
- Was historical evidence duplicated unnecessarily?

## Git delivery

- Is the work on the correct task branch?
- Are unrelated user changes preserved?
- Are all task changes committed when the delivery mode requires it?
- Is the final verified commit pushed when required?
- Does a reviewable PR exist for every freshly pushed task branch?
- Does the PR target the correct base branch?
- Does the PR body match the final diff?
- Are actual verification commands/results included?
- Are remaining task-related uncommitted changes explicitly justified?

## Wayfinder

If the task belongs to a Wayfinder map:

- Is the current ticket actually terminal?
- Are all other required map tickets accounted for?
- Did any hard acceptance condition fail?
- Is required evidence present?
- Does implementation match the frozen decision?
- Is the map complete, blocked, or still in progress?
- If complete, does the handoff stop instead of starting the next map automatically?

## Final decision

Only declare the task complete when all applicable required items are satisfied.

If not, report the exact blocker and next authorized action.
