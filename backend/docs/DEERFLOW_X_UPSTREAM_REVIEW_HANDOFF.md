# DeerFlow-X Upstream Review Handoff

Status: active handoff
Date: 2026-06-29
Project root: `/Users/avo/aicos/projects/deerflow-x`
Current demo worktree: `/Users/avo/aicos/projects/deerflow-x/pr-stack/13-latest-demo`
Current demo branch: `codex/deerflow-x-latest-demo`

This document is for agents continuing DeerFlow-X work. It records the current
upstream review state, what must be fixed before asking maintainers for deeper
review, and how to keep the PR stack upstream-friendly.

## Current Local State

The local demo branch contains the integrated runtime, Work Module, and
WorkBoard demo. It is useful for local validation, but it is not the right shape
to send upstream as one PR.

Important recent demo commits:

- `a57eff29 fix(work): reduce work module runtime overhead`
- `e83261c3 fix(work): inject scoped work unit tool context`
- `36e24cdc fix(work): improve board and chat scrolling`

These commits should be split/backported into the narrower upstream PR branches
instead of being reviewed as a single demo branch.

## Upstream PR State

Repository: `bytedance/deer-flow`

Open PRs from `mjnkao`:

- #3813 `docs: define durable workflow runtime stack` - draft
- #3814 `feat(runtime): add durable workflow store` - draft
- #3815 `feat(runtime): expose durable workflow APIs` - draft
- #3816 `feat(runtime): bind runs to workflow traces` - draft
- #3817 `feat(work): add generic work unit module` - draft
- #3818 `feat(work): expose work unit agent tools` - draft
- #3819 `feat(work): add work board workspace` - draft
- #3848 `feat(runtime): reconcile orphaned durable workflows` - open
- #3849 `feat(runtime): add deterministic workflow binding resolver` - open
- #3850 `feat(runtime): route channel runs through workflow intake` - open
- #3851 `feat(runtime): track durable workflow waiting and resume refs` - open
- #3852 `feat(runtime): prepare durable workflow worker leases` - open

As of 2026-06-29, GitHub reports the branches as mergeable, but review state is
`REVIEW_REQUIRED`. The important blocker is process, not only code.

### CLA Blocker

CLA means Contributor License Agreement. DeerFlow uses CLAassistant. The bot is
reporting `license/cla` as pending/not signed on the submitted PRs.

This must be handled by the GitHub account owner, not by code changes:

1. Open one of the CLAassistant links on the PRs.
2. Sign the CLA with the `mjnkao` GitHub account.
3. Use the CLAassistant recheck link if the status does not update.

Do not ask maintainers for code review until the CLA check is green.

### Maintainer Feedback

PR #3849 has maintainer feedback from `WillemJiang` saying the feature is large
and needs RFC/background/user story before the implementation stack can be
evaluated.

Treat this as the main upstream acceptance signal:

- lead with problem statement and user stories;
- show why DeerFlow needs a minimal runtime envelope in addition to LangGraph
  checkpointing;
- keep Work Module, WorkBoard, PM adapters, and visual workflow designer as
  follow-up modules;
- make PR 1-5 the first reviewable runtime milestone.

## Recommended Upstream Strategy

The current implementation direction is still valid, but the review packaging
should change.

### 1. Update PR #3813 Into The RFC Anchor

PR #3813 should become the clear RFC/background PR.

It should explain:

- DeerFlow already has LangGraph checkpointer/store, RunManager, RunRepository,
  RunEventStore, gateway execution, and channel adapters.
- The gap is not LangGraph checkpoint durability.
- The gap is a DeerFlow-owned durable intake/workflow envelope that gives every
  external message or run request stable identity, idempotency, runtime refs,
  event projection, and recovery visibility.
- LangGraph remains the owner of graph execution, checkpoint state, interrupt
  payloads, graph-local memory, and resume semantics.
- DeerFlow owns generic intake, run orchestration, event correlation, routing,
  and recovery visibility.

Use this RFC framing before pushing maintainers to review the rest of the stack.

### 2. Reply To PR #3849 With The RFC Framing

Reply to the maintainer comment with a short note:

- acknowledge that the stack needs RFC/background first;
- point to updated #3813;
- say the later runtime PRs can stay as implementation follow-ups;
- ask specifically whether the minimal durable workflow envelope belongs in
  DeerFlow core.

Do not argue for WorkBoard or PM integration in that reply. Keep the reply about
the runtime envelope.

### 3. Rebase The Stack Onto Current `upstream/main`

The upstream base has moved since the PRs were opened. Before asking for serious
review, rebase each PR branch onto current `upstream/main` and rerun relevant
tests.

Use `--force-with-lease`, not plain force push.

Suggested order:

1. `codex/deerflow-durable-runtime-docs`
2. `codex/deerflow-durable-workflow-store`
3. `codex/deerflow-durable-workflow-api`
4. `codex/deerflow-durable-run-wrapper`
5. `codex/deerflow-durable-recovery`
6. `codex/deerflow-durable-binding-resolver`
7. `codex/deerflow-durable-channel-intake`
8. `codex/deerflow-durable-waiting-resume`
9. `codex/deerflow-workflow-worker-readiness`

Keep Work Module and WorkBoard branches separate and draft until runtime
direction is accepted.

### 4. Backport Local Fixes Into The Right PRs

Do not update upstream PRs by pushing the integrated demo branch. Split the demo
fixes by module boundary.

Backport guidance:

- `e83261c3 fix(work): inject scoped work unit tool context`
  belongs with Work Unit agent tools, because it fixes the agent's ability to
  receive scoped Work Unit tool context and update real Work Unit state.

- backend parts of `a57eff29 fix(work): reduce work module runtime overhead`
  belong with Work Unit agent tools/config. The key upstream-friendly rule is:
  `modules.work.global_tools_enabled=false` by default, while scoped Work Unit
  tools remain available to WorkBoard or another bound runtime surface.

- frontend parts of `a57eff29` belong with WorkBoard MVP. The board should lazy
  load chat/trace panels and avoid aggressive polling so WorkBoard does not
  make normal DeerFlow heavier.

- `36e24cdc fix(work): improve board and chat scrolling` belongs with WorkBoard
  MVP.

- auth/CSRF demo stability fixes should be considered separately. Do not mix
  generic auth fixes into Durable Workflow or Work Module PRs unless they are
  required by that PR's tests.

### 5. Keep PRs Modular

The stack should preserve value when later PRs are rejected:

- PR 1-5: durable workflow identity and trace value without Work Module.
- PR 6-9: recovery, binding, channel intake, waiting/resume improvements.
- PR 10: worker-readiness only; runtime still works without it.
- Work Module: optional operational work tracking.
- WorkBoard: optional UI app over Work Module.

If Work Module or WorkBoard is rejected, Durable Workflow Runtime must still
work.

## RFC Draft For Maintainer Discussion

Use this as the basis for PR #3813 and the reply on #3849.

```markdown
## RFC: Durable Workflow Runtime Layer for DeerFlow

Thanks for the feedback. I agree this stack should start with clearer
background and user stories before asking maintainers to review the full
implementation.

### Background

DeerFlow already has a strong LangGraph-based runtime foundation:

- LangGraph checkpointer for graph/thread checkpoint state.
- LangGraph store for runtime/cross-thread memory.
- RunManager / RunRepository for run identity, status, cancellation, and
  multitask behavior.
- RunEventStore for ordered run event streams.
- Gateway execution through process-local asyncio tasks and agent streaming.
- Channel adapters for external message sources.

This gives DeerFlow a durable agent runtime, but not yet a durable workflow
intake/orchestration layer.

The current gap is not LangGraph checkpointing itself. LangGraph should
continue to own graph execution, checkpoint state, interrupts, and graph-local
memory. The missing layer is a DeerFlow-level durable envelope around incoming
work so that every external message or API/dashboard request can be correlated
with stable workflow identity, external source refs, idempotency, runtime refs,
status, event timeline, and recovery hints.

### User Stories

1. As an operator, I want every incoming agent request to have a durable
   workflow record so I can inspect status and history even after a gateway
   restart.
2. As an integration developer, I want dashboard/API/channel messages to enter
   DeerFlow through the same durable intake contract, with idempotency and
   source refs, without channel-specific runtime logic.
3. As an enterprise user, I want stable workflow identity that can later be
   linked to external systems such as Jira, ClickUp, Plane, Trello, Lark, or
   internal task systems.
4. As a DeerFlow maintainer, I want this layer to remain optional, minimal, and
   compatible with existing run APIs and LangGraph ownership boundaries.

### Proposed Scope

Add a small optional Durable Workflow Runtime Layer with:

- `workflow_id`
- `external_message_ref`
- source/channel metadata
- `thread_id`
- `run_id`
- checkpoint refs
- `idempotency_key`
- workflow status
- append-only workflow events
- created/updated timestamps
- generic metadata

Runtime responsibilities:

- durable workflow intake;
- idempotent create-or-get;
- binding workflow refs to existing DeerFlow runs;
- workflow event projection over existing RunEventStore;
- recovery semantics for orphaned active workflows;
- optional waiting/resume refs for human-in-the-loop observability;
- future worker lease primitives without enabling a required worker service.

### Non-goals

This does not replace LangGraph durability. LangGraph remains responsible for
graph execution, checkpoint state, interrupt payloads, graph-local memory, and
resume mechanics.

This RFC also does not propose hard dependencies on Temporal, Restate, Hatchet,
AICOS, or any external PM tool.

### Why Not Start With Temporal / Restate / Hatchet?

Temporal, Restate, and Hatchet are useful references for durable workflow
design, especially around workflow identity, retries, leases, idempotency, and
recovery. But adding one as a hard dependency would make DeerFlow heavier and
harder to adopt.

The proposed approach is to build a minimal native DeerFlow durable workflow
envelope, keep it generic, preserve LangGraph as the execution/checkpoint owner,
and leave external orchestrator adapters as optional future integrations.

### Relationship To Work Module / Work Board

The Durable Workflow Runtime Layer should be independent.

A later optional Work Module can build on top by introducing a generic Work Unit
primitive. A Work Unit can map to external PM concepts such as task/card/issue/
ticket, but DeerFlow core should keep the primitive generic.

A Work Board can then be an optional Trello-style UI using the Work Module. It
should not be required for the durable runtime to work.

### Compatibility

- Existing run APIs keep their current behavior and response shape.
- Durable workflow behavior is feature-gated.
- Clients can ignore workflow fields if they do not use them.
- No AICOS-specific concepts are introduced.
- No external orchestrator dependency is required.

### Review Request

Before continuing with the full stack, I would like maintainer feedback on:

- whether this durable workflow envelope belongs in DeerFlow core;
- whether the LangGraph/DeerFlow ownership boundary is acceptable;
- whether the proposed primitive set is small enough;
- whether Work Module and WorkBoard should remain separate follow-up PRs;
- whether any part should be reduced further for an initial merge.
```

## Work Module And WorkBoard Acceptance Rules

Use `Work Unit` as the DeerFlow term. Avoid reintroducing `work item` or using
`task` as the core schema name. External systems may map Work Units to tasks,
cards, issues, tickets, or requests.

Work Module should be accepted on its own only if it remains:

- generic enough to map to PM tools later;
- independent from WorkBoard;
- independent from Durable Workflow Runtime except for optional refs;
- feature-gated by `modules.work`;
- light when disabled.

WorkBoard should be accepted on its own only if it remains:

- an optional UI app over Work Module;
- useful without Jira/Trello credentials;
- lazy enough not to slow normal DeerFlow chat;
- dependent on Work Module API, not on custom board-only state.

Agent status changes must be real tool writes. If an agent says it moved a Work
Unit from `ready` to `in_progress`, it must have called the scoped or global
Work Unit tool and the WorkBoard must reflect the stored status.

## Immediate Next Actions

1. Push the latest local demo branch so the current local fixes are not lost.
2. Sign/recheck CLA.
3. Update PR #3813 with the RFC framing above.
4. Reply to PR #3849 with a short RFC pointer.
5. Rebase runtime PR branches onto current `upstream/main`.
6. Backport local fixes into the narrow PR branches.
7. Run focused tests per PR and update PR descriptions with current results.
8. Keep Work Module and WorkBoard draft until the runtime foundation direction
   has maintainer buy-in.
