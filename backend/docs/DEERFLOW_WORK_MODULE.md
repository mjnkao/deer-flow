# DeerFlow Work Module

Status: architecture decision
Date: 2026-06-26
Scope: generic work unit schema, workflow linkage, agent tool boundary, and PM-tool adapter boundary

## Decision

DeerFlow should add an optional Work Module after the Durable Workflow Runtime
foundation. The module gives teams a small, generic way to track operational
work that can be performed by humans, agents, or both. It should stay easy to
map to external PM tools such as Jira, Trello, ClickUp, Plane, Lark, GitHub
Issues, or enterprise work management systems.

The Work Module should not be part of the minimal Durable Workflow Runtime
Layer. Runtime workflow identity, idempotency, status, and event correlation
must work without work units. Work units sit above the runtime and may link to
workflow envelopes, DeerFlow threads, runs, artifacts, and external objects.

Use `work_unit` as the canonical DeerFlow core term. Integrations may call the
same concept a task, card, issue, ticket, work unit, or request.

## Boundary

Durable Workflow Runtime owns:

- `workflow_id`;
- intake/source/idempotency metadata;
- workflow lifecycle status;
- workflow events and run event correlation;
- thread/run/checkpoint refs.

Work Module owns:

- `work_unit_id`;
- title, description/objective, status, priority, assignee, due date, labels;
- work-to-work links;
- acceptance criteria and lightweight gates;
- external PM object bindings;
- optional links to workflow/thread/run refs;
- work unit events for audit and board activity.

The future WorkBoard application owns:

- visual board/list views over Work Module records;
- local backlog capture UX;
- status projection and review UX over runtime/adapter updates;
- filters and trace links;
- no separate task schema.

## Module Gates

The Work Module is an optional layer over DeerFlow's runtime:

```yaml
modules:
  durable_workflows:
    enabled: true
    api_enabled: true
    auto_envelope_for_runs: true
  work:
    enabled: true
    api_enabled: true
    global_tools_enabled: false
```

- `durable_workflows.enabled=false` preserves the legacy run path with no
  automatic workflow envelope.
- `work.enabled=false` disables Work Unit store construction and Work Unit API
  exposure.
- `work.global_tools_enabled=false` keeps the generic `work_units` tool out of
  normal chat/tool schemas. Runtime surfaces can still attach a scoped
  `work_unit` tool to a single bound work unit.
- A future WorkBoard UI can depend on Work Module, but Work Module must not
  depend on WorkBoard.

The first implementation keeps Work tables in DeerFlow's normal database
migration chain. When the module is disabled those tables are inert; API, store,
and UI surfaces are not mounted. A separate migration namespace can be added
later if upstream maintainers want a zero-table footprint for disabled modules.

PM adapters own:

- mapping external task/card/issue/ticket fields to `work_units`;
- sync cursors and conflict policy;
- external webhooks and credentials;
- tool-specific custom fields.

## Core Schema

### `work_units`

Minimum fields:

- `work_unit_id`: DeerFlow-generated id.
- `title`: short human-readable title.
- `description`: optional Markdown/plain text body.
- `status`: `backlog`, `ready`, `in_progress`, `blocked`, `review`, `done`,
  `closed`, or `cancelled`.
- `priority`: `P0`, `P1`, `P2`, `P3`, or `P4`.
- `assignee_ref`: optional user/team/external assignee ref.
- `reporter_ref`: optional source reporter ref.
- `due_at`: optional target date.
- `workflow_id`: optional Durable Workflow Runtime link.
- `thread_id`: optional DeerFlow thread link.
- `run_id`: optional DeerFlow run link.
- `source_type`: `local`, `pm_tool`, `channel`, `api`, or `other`.
- `source`: provider/system name.
- `external_type`: optional provider object type such as `jira_issue`,
  `trello_card`, `clickup_task`, or `plane_issue`.
- `external_ref`: provider object id/key.
- `external_url`: provider object URL.
- `labels`: JSON string array.
- `metadata`: JSON extension object.
- `created_at`, `updated_at`.

Indexes:

- `(status, updated_at)`;
- `(priority, updated_at)`;
- `(workflow_id)`;
- `(thread_id, run_id)`;
- `(source_type, source, external_ref)` unique when `external_ref` exists.

### `work_events`

Minimum fields:

- `work_event_id`;
- `work_unit_id`;
- `seq`;
- `event_type`;
- `actor_ref`;
- `workflow_id`;
- `run_id`;
- `content`;
- `metadata`;
- `created_at`.

Use this for board activity and adapter sync audit, not for LangGraph
checkpoint state.

### Later Tables

Keep the first PR small. Add these only when workflows need them:

- `work_unit_links`: relates work units with `blocks`, `blocked_by`,
  `duplicates`, `relates_to`, `parent`, `child`.
- `work_unit_criteria`: acceptance criteria or completion checks.
- `work_gates`: pending approvals/human decisions linked to work units and
  workflow waits.
- `external_object_bindings`: richer adapter binding metadata and sync state.

## PR Sequence

Work Module PRs should follow the runtime PRs. They are useful even if the
visual workflow designer is not accepted.

### Work PR 1: Core Module

- Add this document.
- Add `work_units` and `work_events` models/migrations.
- Add memory and SQL repositories.
- Add tests for create/list/update/link-to-workflow.
- Add `GET /api/work-units`.
- Add `POST /api/work-units`.
- Add `GET /api/work-units/{work_unit_id}`.
- Add `PATCH /api/work-units/{work_unit_id}`.
- Add `GET /api/work-units/{work_unit_id}/events`.
- Add a runtime-bound Work Unit tool so agents must call a tool before claiming
  a status change.

### Work PR 2: Agent Tools

- Expose a global `work_units` tool only when explicitly enabled by module
  config.
- Let agents create, list, inspect, and update generic work units through the
  same store/API contract as external PM adapters.
- Keep runtime-bound `work_unit` updates scoped to the work unit attached by
  the calling surface.
- Record tool writes as `work_events` so UI and adapters can audit agent
  actions.

### Work PR 3: WorkBoard MVP

- Add `/workspace/work` route.
- Show board columns by status.
- Create local backlog work units.
- Let agent/runtime updates move status through the Work Unit tool/API.
- Link to thread/run/workflow trace when refs exist.

### Work PR 4: External PM Binding Contract

- Add adapter interface docs and sync metadata conventions.
- Add import/export examples for Trello/Jira/Plane-style objects.
- No hard dependency on a PM vendor.

### Work PR 5: Gates And Criteria

- Add acceptance criteria and lightweight human gates.
- Link gates to durable workflow `waiting` states where applicable.
- Keep LangGraph interrupt payloads in LangGraph checkpoints.

## Local Demo Path

The smallest useful demo is Work PR 1-3:

1. Create a work unit from the WorkBoard.
2. Ask the assigned agent to inspect or update it through the Work Unit tool.
3. Attach a `workflow_id` or `run_id` from a normal DeerFlow chat.
4. Open the workflow trace from the work unit.

This proves the product value without needing Jira/Trello credentials, a visual
designer, or an external orchestrator.
