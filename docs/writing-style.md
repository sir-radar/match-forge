# Engineering Writing Style

## Purpose

Use this guide for substantial plans, Wayfinder tickets, research notes, ADRs, pull requests, durable documentation, and user-facing engineering explanations.

Write like an experienced engineer communicating with another engineer.

Clarity beats sophistication.

## Plain language

Prefer the simplest accurate word or phrase.

Prefer:

```text
order
history
timeline
main
shared
source
original data
saved data
mapping
match
compare
difference
decision
rule
version
input
output
record
file
data
update
change
check
proof
test
result
```

Avoid unnecessary abstract language such as:

```text
chronology
canonicalize
canonicalization
substrate
corroborate
corroboration
instantiate
instantiation
materialize
materialization
ontology
taxonomy
evidence boundary
resolution surface
identity surface
source-of-truth surface
decision topology
```

Some technical words are valid when they are part of an established MatchForge contract. Do not remove precision merely to simplify prose.

## Examples

```text
BAD:
preserve event chronology

GOOD:
preserve event order
```

```text
BAD:
resolve to the canonical team

GOOD:
map to the MatchForge team
```

```text
BAD:
canonical match identity

GOOD:
MatchForge match ID
```

```text
BAD:
preserve provider provenance

GOOD:
keep the original provider and source details
```

```text
BAD:
materialize the acceptance corpus

GOOD:
create the acceptance dataset
```

```text
BAD:
instantiate the frozen contract

GOOD:
implement the agreed contract
```

```text
BAD:
corroborate the result

GOOD:
confirm the result against the second source
```

```text
BAD:
temporal semantics

GOOD:
date and time rules
```

```text
BAD:
knowledge-time semantics

GOOD:
rules for when the data was known
```

```text
BAD:
immutable source lineage

GOOD:
keep a trace from the processed data back to the exact original file
```

## Do not invent abstract terminology

Do not create new architecture nouns merely to make a decision sound more formal.

Avoid:

```text
X boundary
X surface
X substrate
X authority
X evidence layer
X semantic layer
X resolution plane
X decision topology
```

unless the repository already defines the term and it materially improves accuracy.

Describe what the code or process actually does.

```text
BAD:
The identity-resolution boundary preserves provider provenance.

GOOD:
Provider IDs are mapped to MatchForge IDs, and the original provider ID is kept.
```

## Existing technical names are exempt

Do not rename existing:

- classes;
- interfaces;
- schemas;
- database fields;
- enums;
- APIs;
- protocol names;
- filenames;
- repository-defined contracts;
- established domain terms.

If the repository contains `CanonicalChangeSetV1`, use that exact name.

Surrounding prose should still be natural:

```text
BAD:
CanonicalChangeSetV1 materializes the canonical mutation chronology.

GOOD:
CanonicalChangeSetV1 records which MatchForge data changed and which source caused the change.
```

Use `canonical` when it is part of an existing technical name or when removing it would reduce accuracy. Do not use it casually as a synonym for "main", "shared", "internal", "approved", or "MatchForge".

## Avoid AI-style specification prose

Avoid:

- abstract noun stacking;
- excessive formal transitions;
- repetitive restatement;
- fake precision;
- unnecessary capitalization;
- invented contract names;
- philosophical explanations of simple code;
- consultancy-style architecture language.

```text
BAD:
This establishes the canonical temporal substrate through which provider observations are deterministically reconciled.

GOOD:
This maps provider data to MatchForge records using fixed rules.
```

## Contract-name restraint

Do not invent a new `SomethingV1` contract simply because a concept appears in a ticket.

Create a named contract only when it needs a stable machine-readable or code-level interface.

For simple implementation rules, prefer an ordinary:

```text
function
type
configuration
test
documented rule
```

## Comments

Comments should explain why, not restate the code.

Comments are especially useful for:

- numerical tolerances;
- point-in-time exclusions;
- statistical assumptions;
- compatibility decisions;
- provider quirks;
- non-obvious recovery behavior.

## Final writing test

Before finalizing substantial prose, ask:

> Would a senior engineer naturally say this during a code review?

Then ask:

> Can any uncommon word be replaced by a shorter normal word without losing technical accuracy?

If yes, rewrite it.

Prefer writing that is:

```text
simple
specific
concrete
technical
natural
direct
```

over writing that is:

```text
academic
ceremonial
legalistic
consulting-style
AI-generated
over-architected
```
