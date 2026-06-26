# Agent Orchestration Designer for DeerFlow

Status: architecture decision draft
Date: 2026-06-26
Scope: DeerFlow workflow definitions, visual workflow designer, compiler, runtime integration, and plugin extension points

## Decision

DeerFlow should add an optional agent orchestration designer: a visual module
for designing how DeerFlow agents coordinate work. This is not a general
automation builder in the style of n8n or Node-RED. It is an orchestration layer
on top of DeerFlow's agent builder, agent profiles, tools, skills, middleware,
memory, subagents, runs, and LangGraph runtime.

The source of truth should be a DeerFlow-owned Agent Workflow DSL. Visual
editors such as FlowGram or React Flow should import/export that DSL, and
runtime adapters should compile the DSL into LangGraph graphs or DeerFlow
runtime execution plans.

The first upstream-friendly cut should live in DeerFlow core as a generic
agent workflow definition and validation contract, with the designer, APIs,
persistence, and compiler packaged as an optional core module/plugin. A
deployment that does not enable this module should see no behavior change in
chat, agent builder, gateway run APIs, channels, or existing LangGraph runtime
execution.

## Current DeerFlow Foundation

DeerFlow already has most of the lower runtime pieces a workflow platform
needs:

- agent construction through `create_deerflow_agent()` and the config-driven
  lead agent factory;
- agent profiles, skills, tools, middleware, memory, uploads, sandboxing,
  guardrails, token usage, todo/planner middleware, and title/summarization
  middleware;
- subagent delegation through the `task` tool and `SubagentExecutor`;
- LangGraph checkpointer and store providers for thread-scoped state and
  cross-thread memory;
- `RunManager`, `RunStore`, `RunEventStore`, `RunJournal`, stream bridge, and
  gateway run endpoints;
- frontend workspace surfaces for chats, agents, settings, skills, channels,
  artifacts, and run/message rendering;
- `@xyflow/react` is already installed in the frontend.

There is also a draft durable workflow frontdoor in this worktree. That layer
models inbound workflow envelopes and run/checkpoint correlation. It is useful
for workflow *invocation* and external-channel durability, but it is not the
same artifact as an agent workflow *definition*.

## External Research Summary

FlowGram:

- FlowGram is a ByteDance workflow development framework for building AI
  workflow platforms, not a complete hosted workflow product.
- It is MIT licensed, active, and published as `@flowgram.ai/*` packages. The
  npm package set was at `1.0.12` on 2026-06-08.
- It includes free/fixed layout canvases, document models, node registries,
  form engine, variable engine, materials, history/command services, and a
  Node.js runtime package.
- Its docs expose `FlowDocument.fromJSON/toJSON`,
  `WorkflowDocument.onContentChange`, `WorkflowLinesManager.toJSON`, and node
  registration APIs, so import/export and custom node palettes look feasible.
- Risk: it is a larger framework with its own document/runtime concepts. If
  DeerFlow stores FlowGram JSON as canonical runtime truth, DeerFlow becomes
  coupled to FlowGram's editor model.

React Flow:

- React Flow is MIT licensed, mature, heavily adopted, and already present in
  DeerFlow frontend dependencies as `@xyflow/react`.
- It provides node/edge rendering, handles, controls, minimap, custom nodes,
  validation hooks, layout examples, save/restore examples, and workflow UI
  templates.
- Risk: it is canvas infrastructure, not an AI workflow framework. DeerFlow
  would need to build forms, variable/data mapping, validation UX, palettes,
  history, and schema semantics itself.

Rete.js:

- Rete.js is MIT licensed and is a TypeScript-first visual programming
  framework with plugins, React/Vue/Angular/Svelte/Lit renderers, dataflow and
  control-flow engines, import/export, validation, minimap, and undo/redo.
- Risk: it is processing-oriented and engine-centric; integrating it may pull
  DeerFlow toward Rete's graph execution model instead of LangGraph.

LangSmith Studio / LangGraph Studio:

- LangSmith Studio is an agent IDE for visualizing graph architecture,
  interacting with agents, inspecting traversed nodes and intermediate state,
  debugging with time travel, and managing assistants/threads.
- It is excellent for observing and debugging deployed LangGraph-style systems,
  but it is not a general-purpose embedded workflow designer for DeerFlow's
  frontend.

Node-RED / n8n / Dify / Flowise / Langflow:

- Node-RED demonstrates a long-lived palette/editor/runtime model and JSON
  flows, but it is an application/runtime ecosystem, not a light embeddable
  React component.
- n8n shows workflow history, templates, executions, sub-workflows, waiting,
  looping, merging, and rich integrations. Its license is not a fit for direct
  embedding as DeerFlow UI infrastructure.
- Dify shows useful AI app workflow concepts: serial/parallel execution,
  variables from earlier nodes, user input, iteration/loop nodes, copy/paste,
  version control, logs, marketplace, and plugin/tool awareness.
- Flowise and Langflow validate the product shape for visual AI agent/LLM
  workflows, real-time testing, custom components, templates, API serving, MCP,
  and human-in-the-loop support.

References:

- https://github.com/bytedance/flowgram.ai
- https://flowgram.ai/en/api
- https://www.npmjs.com/package/@flowgram.ai/editor
- https://reactflow.dev
- https://retejs.org/docs
- https://docs.langchain.com/langsmith/studio
- https://nodered.org/docs
- https://docs.n8n.io/workflows/
- https://docs.dify.ai/en/use-dify/build/orchestrate-node
- https://docs.flowiseai.com/
- https://docs.langflow.org/

## Recommendation

Use an agent-workflow-DSL-first architecture.

For the editor, keep two paths open:

1. Short-term prototype: use React Flow because DeerFlow already depends on it
   and it is sufficient for a minimal designer with node palette, canvas,
   inspector, validation, and import/export.
2. Parallel spike: evaluate FlowGram as an optional package for a richer
   workflow-builder experience, especially if DeerFlow wants built-in variable
   scope, forms, materials, compound nodes, and editor services.

Do not compile directly from FlowGram or React Flow JSON to LangGraph. Compile
from DeerFlow Agent Workflow DSL to LangGraph/runtime plans. Editor-native
state can live under `node.editor`, `edge.metadata`, or a separate editor
snapshot, but it must not be the canonical runtime artifact.

## Optional Core Module

The feature should be implemented as an optional DeerFlow core module/plugin,
not as always-on product surface.

Minimal module boundaries:

- `deerflow.runtime.workflow_definitions`: schema and graph validation. Safe to
  keep importable because it has no side effects.
- `deerflow.workflow_designer.api`: optional gateway routers for CRUD,
  validation, run, import, and export. Mounted only when enabled.
- `deerflow.workflow_designer.persistence`: optional DB repositories and
  migrations for definitions, versions, and workflow runs.
- `deerflow.workflow_designer.compiler`: optional compiler registry that lowers
  agent workflow nodes into executable LangGraph/runtime plans.
- `frontend/workflow-designer`: optional workspace route and components.
- `workflow node packs`: optional packages for built-in and third-party nodes.

Activation should be explicit, for example:

```yaml
workflow_designer:
  enabled: false
  editor: react-flow
  persistence: database
  builtin_node_packs:
    - deerflow.agent
    - deerflow.tool
    - deerflow.human
```

When disabled:

- no workflow designer routes are mounted;
- no frontend navigation item is shown;
- no workflow tables are created unless migrations are explicitly applied;
- existing `/runs`, `/threads`, channels, agent builder, skills, and tools keep
  their current behavior;
- the lightweight schema package may still exist for SDK consumers and tests.

## Agent Workflow DSL

The initial DSL should contain:

- `workflow_id`, `version`, `name`, `description`;
- `input_schema`, `output_schema`;
- `nodes`, `edges`;
- per-node `config`, `input_schema`, `output_schema`, `runtime_hints`,
  `editor`;
- per-edge `source`, `target`, ports, condition, and data mapping;
- `validation_rules`, `runtime_hints`, and `metadata`.

Built-in node types:

- `start`
- `agent_task`
- `agent_handoff`
- `subagent_task`
- `router_agent`
- `tool_call`
- `skill_context`
- `human_input`
- `approval`
- `condition`
- `parallel_agents`
- `join`
- `loop`
- `retry`
- `memory_context`
- `evaluation`
- `artifact_output`
- `end`

Agent-centric nodes should bind to existing DeerFlow agent-builder artifacts by
reference, not copy their full definitions into a workflow. For example, an
`agent_task` node should reference an `agent_id` or agent profile name, then
optionally constrain task prompt, model, skills, tools, timeout, retry policy,
and output schema for this step.

Example:

```json
{
  "id": "research_step",
  "type": "agent_task",
  "config": {
    "agent_id": "researcher",
    "task": "Research the user's question and return cited findings.",
    "input_mapping": {
      "question": "$workflow.input.message"
    },
    "allowed_tools": ["web_search", "read_file"],
    "enabled_skills": ["deep-research"],
    "output_schema": {
      "findings": "array",
      "citations": "array"
    }
  }
}
```

A `tool_call` node is intentionally different from an agent node. It invokes a
known tool directly, without asking an LLM to decide what to do:

```json
{
  "id": "create_ticket",
  "type": "tool_call",
  "config": {
    "tool_name": "create_issue",
    "args": {
      "title": "$nodes.summarize.output.title",
      "body": "$nodes.summarize.output.body"
    },
    "requires_approval": true
  }
}
```

The DSL should remain upstream-friendly but not so generic that it loses
DeerFlow's agent-platform identity. DeerFlow core can own generic agent
orchestration concepts such as agent task, tool call, skill context, memory,
human input, approval, condition, and artifact output. AICOS-like concepts such
as Work Unit, Gate, Evidence, Context Packet, and Runtime Invocation can be
represented by external node packs or integration metadata, but DeerFlow core
should not hard-code those names.

## Runtime Architecture

Recommended layering:

```text
Agent builder
  -> agent profiles / tools / skills / middleware

Agent orchestration designer
  -> DeerFlow Agent Workflow DSL
  -> validation and definition versioning

Compiler
  -> LangGraph graph or DeerFlow runtime plan

Durable workflow layer
  -> workflow run identity / idempotency / status / retry / resume refs
  -> RunManager / RunEventStore / Checkpointer
  -> workflow run projection APIs
```

DeerFlow core owns:

- workflow definitions and versions;
- workflow validation;
- generic workflow run records and step event projection;
- compiler interfaces;
- built-in agent orchestration node packs;
- API boundaries for CRUD, validate, run, inspect, import, and export.

LangGraph owns:

- graph execution;
- checkpoint values;
- `thread_id`, `checkpoint_ns`, and `checkpoint_id`;
- interrupts/resume mechanics;
- graph-local state replay.

Visual editor packages own:

- canvas rendering;
- editor-only layout and selection state;
- palette and inspector UX;
- local validation display.

Integrations own:

- domain-specific task semantics;
- approval policies;
- evidence/artifact acceptance;
- external channel routing beyond generic DeerFlow refs.

## Durable Workflow Layer Relationship

The durable workflow layer and the agent orchestration designer should be built
in parallel, but they are different planes:

- Durable workflow layer: runtime/invocation/control plane. It owns intake,
  idempotency, source refs, status transitions, durable run identity,
  restart/orphan handling, retry policy, waiting/resume refs, and binding to
  `thread_id`, `run_id`, `checkpoint_ns`, and `checkpoint_id`.
- Agent orchestration designer: definition/design plane. It owns the versioned
  Agent Workflow DSL, visual editing, validation, node config, data mapping,
  and the compiler input.

The durable layer should not depend on FlowGram, React Flow, or any editor UI.
The designer should not invent its own runtime durability semantics. They meet
through shared contracts: workflow definition id, definition version, workflow
run id, LangGraph thread/run/checkpoint refs, status model, and event
projection.

Recommended dependency direction:

```text
WorkflowDefinition(versioned DSL)
  -> compiler
  -> DurableWorkflowRun
  -> DeerFlow RunManager / LangGraph thread / checkpoint
```

The durable layer can run simple chat-agent invocations without a designed
workflow. The designer can validate and version definitions without executing
them. The first real integration happens when a compiled workflow definition
creates a durable workflow run.

## Shared Contracts

These identifiers should be settled before large UI or compiler work:

- `workflow_definition_id`: stable id for an agent workflow definition.
- `workflow_definition_version`: immutable version number or id for a DSL
  snapshot.
- `workflow_run_id`: durable id for one execution of a designed workflow.
- `frontdoor_workflow_id`: durable intake/envelope id for an inbound message or
  command, when the run came through the frontdoor.
- `thread_id`: LangGraph/DeerFlow conversation state id.
- `run_id`: DeerFlow run id managed by `RunManager`.
- `checkpoint_ns`: LangGraph checkpoint namespace.
- `checkpoint_id`: LangGraph checkpoint reference for resume/debug.
- `step_id`: DSL node id or compiler-generated stable step id.
- `node_pack_refs`: required node packs and versions for validation/import.

Status contracts should be compatible but not identical:

- Frontdoor/envelope statuses: `received`, `bound`, `run_created`, `running`,
  `waiting`, `succeeded`, `failed`, `cancelled`, `orphaned`, `ignored`.
- Definition version statuses: `draft`, `published`, `deprecated`,
  `archived`.
- Workflow run statuses: `pending`, `running`, `waiting`, `succeeded`,
  `failed`, `cancelled`, `orphaned`.
- Step statuses: `pending`, `running`, `waiting`, `succeeded`, `failed`,
  `skipped`, `cancelled`.

The event model should initially project from `RunEventStore` plus workflow
step correlation metadata. It should avoid duplicating LangGraph checkpoint
state or large transcripts.

## Persistence and Versioning

Start with database-backed workflow definitions:

- `workflow_definitions`: latest mutable metadata, owner/workspace, active
  version, archived flag.
- `workflow_definition_versions`: immutable JSON DSL snapshots, version number,
  status (`draft`, `published`, `deprecated`), created_by, timestamps.
- `workflow_runs`: workflow definition/version refs, optional frontdoor envelope
  ref, `thread_id`, `run_id`, `checkpoint_ns`, `checkpoint_id`, status, input
  summary, output summary, error, metadata.
- `workflow_step_events` can initially be a projection over `RunEventStore`
  plus workflow step correlation metadata rather than a duplicate canonical log.

File-based project config and marketplace templates should be import/export
formats, not the only persistence layer. This lets dashboard, API, channels,
and deployed agents share the same workflow definitions.

## Run Identity

A designed workflow run should bind:

```text
workflow_run_id
  -> workflow_definition_id + workflow_definition_version
  -> optional frontdoor_workflow_id
  -> thread_id
  -> run_id
  -> checkpoint_ns/checkpoint_id
```

Simple chat agent runs continue to work as they do today. A designed workflow
run is different because it has a definition version, step-level intent, and
compiler/runtime metadata. Hybrid runs are allowed: an agent node may reason
inside a workflow constraint, or a workflow may hand off to a subagent through
the existing task tool.

## Compiler Mapping

Initial compile mapping:

- `agent_task`: resolve the referenced DeerFlow agent profile, assemble its
  model/tools/skills/middleware through the existing agent factory path, invoke
  it with step-specific task/input constraints, then write structured output to
  workflow state.
- `agent_handoff`: transfer ownership/context to another agent profile and
  continue from that agent's node.
- `subagent_task`: invoke the existing subagent/task-tool execution semantics.
- `router_agent`: let a bounded agent choose the next branch from an explicit
  allowed set.
- `tool_call`: resolve a DeerFlow tool by name and call it directly with mapped
  args; optionally gate through `approval`.
- `skill_context`: constrain or preload skills for downstream agent nodes.
- `memory_context`: read/write LangGraph store or DeerFlow memory before/after
  agent execution.
- `human_input` and `approval`: compile to LangGraph `interrupt()` and resume
  with `Command(resume=...)`.
- `condition`: compile to `add_conditional_edges`.
- `parallel_agents`: compile to multiple outgoing edges or `Send` fan-out.
- `join`: merge state from parallel branches through explicit reducers.
- `loop` and `retry`: compile to conditional edges plus bounded counters and
  retry policy metadata.
- `evaluation`: run deterministic or model-based checks before allowing a
  workflow to continue.
- `artifact_output`: publish file/message/report output through existing
  artifact facilities.

## Plugin Model

Add plugin contracts after the core DSL:

- `WorkflowNodeProvider`: contributes node type metadata, defaults, inspector
  schema, and icons.
- `WorkflowValidator`: validates whole-graph or node-pack-specific rules.
- `WorkflowCompilerAdapter`: lowers selected node types to executable steps.
- `WorkflowEditorAdapter`: maps DSL to/from FlowGram, React Flow, or another
  editor snapshot.

Node packs should be independently versioned. Workflow definitions should
record required node packs and versions so import/export validation can explain
missing capabilities.

## API Surface

Initial endpoints:

- `POST /api/workflow-definitions`
- `GET /api/workflow-definitions`
- `GET /api/workflow-definitions/{workflow_id}`
- `POST /api/workflow-definitions/{workflow_id}/versions`
- `POST /api/workflow-definitions/validate`
- `POST /api/workflow-definitions/{workflow_id}/run`
- `GET /api/workflow-runs/{workflow_run_id}`
- `GET /api/workflow-runs/{workflow_run_id}/events`
- `POST /api/workflow-definitions/import`
- `GET /api/workflow-definitions/{workflow_id}/export`

## Combined Roadmap with Durable Workflow Layer

Work can proceed in parallel across durable runtime and designer tracks, but
shared contracts should land early.

### Phase 0: Contract Alignment

1. Unify terminology across durable workflow frontdoor and agent orchestration
   designer.
2. Decide id names and status enums for definition, definition version,
   frontdoor envelope, workflow run, and step projection.
3. Document the dependency boundary: durable layer never depends on editor UI;
   designer never owns idempotency/retry/orphan semantics.

### Phase 1: Durable Runtime Foundation

1. Durable frontdoor/envelope minimal implementation:
   - intake id;
   - idempotency key;
   - source/conversation/message refs;
   - `thread_id`, `run_id`, `checkpoint_ns`, `checkpoint_id`;
   - status transitions.
2. Bind existing `/runs`, `/threads/{thread_id}/runs`, and channel ingestion to
   the frontdoor envelope where appropriate.
3. Startup reconciliation for orphaned envelopes/runs.
4. Tests for idempotency, binding, user isolation, and orphan marking.

This phase should not require workflow definitions or a visual designer.

### Phase 2: Agent Workflow Definition Plane

1. Agent Workflow DSL schema and validation library.
2. Built-in node type contract for `start`, `agent_task`, `tool_call`,
   `human_input`, `approval`, `condition`, `artifact_output`, and `end`.
3. Node pack metadata contract for palette/inspector schemas.
4. Definition/version persistence behind `workflow_designer.enabled`.
5. CRUD, validate, import, and export APIs behind the same feature flag.

This phase can run in parallel with Phase 1 after shared contracts are agreed.

### Phase 3: Run Binding Between Both Planes

1. Add `workflow_runs` for designed workflow executions.
2. Bind `workflow_run_id` to:
   - `workflow_definition_id`;
   - `workflow_definition_version`;
   - optional frontdoor envelope id;
   - `thread_id`;
   - `run_id`;
   - checkpoint refs.
3. Add workflow run read APIs and event projection over `RunEventStore`.
4. Ensure simple chat runs remain supported without workflow definitions.

This is the first phase that requires both durable runtime and definition
contracts to agree.

### Phase 4: Compiler and Minimal Execution

1. Compiler interface and registry.
2. Minimal compiler for a linear flow:
   `start -> agent_task|tool_call -> end`.
3. Compile `human_input` and `approval` to LangGraph `interrupt()` and resume
   routes through the durable layer.
4. Add run events that correlate LangGraph/run events to workflow step ids.
5. Tests for run binding, success/failure, waiting/resume, and cancellation.

### Phase 5: Designer UI Prototype

1. Optional frontend route behind feature flag.
2. React Flow prototype using existing `@xyflow/react` dependency.
3. Node palette from node pack metadata.
4. Inspector panel for agent profile, tool, skill, input/output mapping,
   approval, and condition config.
5. Validate/import/export JSON.
6. Run/test button that creates a designed workflow run through the backend.

This can start earlier as a mock/prototype, but production run/test should wait
for Phase 3/4 contracts.

### Phase 6: Rich Orchestration Nodes

1. Agent handoff and router agent.
2. Parallel agents and join.
3. Loop and retry.
4. Subagent task.
5. Skill context and memory context.
6. Evaluation node.
7. Artifact output improvements.

### Phase 7: Optional Editor and Ecosystem

1. FlowGram optional-package spike and dependency-risk report.
2. Plugin interface for custom workflow nodes, validators, compiler adapters,
   and editor adapters.
3. Template/marketplace import/export format.
4. Optional AICOS-X example integration outside DeerFlow core.

## Suggested PR Stack

1. Research/design doc and shared glossary for durable workflows plus agent
   orchestration designer.
2. Durable frontdoor/envelope schema, store, and idempotency tests.
3. Frontdoor binding for existing run/channel entrypoints.
4. Startup reconciliation for orphaned durable workflow envelopes.
5. Agent Workflow DSL schema and validation library.
6. Feature flag/config for optional workflow designer module.
7. Workflow definition/version persistence and migrations behind the flag.
8. Workflow definition CRUD/validate/import/export API behind the flag.
9. Workflow run model binding definition versions to frontdoor/run/checkpoint
   refs.
10. Workflow run event projection over `RunEventStore`.
11. Compiler interface and linear `agent_task`/`tool_call` execution.
12. HITL/approval compile path through LangGraph interrupt and durable resume.
13. React Flow designer prototype behind feature flag.
14. Built-in node pack metadata for agent, tool, human, condition, artifact,
    and end nodes.
15. Agent handoff/router/parallel/join/loop/retry/subagent/memory/evaluation
    nodes.
16. FlowGram optional adapter spike.
17. Custom node/plugin API.
18. Optional AICOS-X integration example outside DeerFlow core.

## First Implemented Slice

This draft introduces `deerflow.runtime.workflow_definitions` with:

- `WorkflowDefinition`
- `WorkflowNode`
- `WorkflowEdge`
- `WorkflowNodeType`
- `validate_workflow_definition()`
- structured validation errors/warnings

The slice validates duplicate identities, required start/end nodes, unknown
edge endpoints, invalid start/end edge direction, reachability, and unreachable
node warnings. It intentionally does not persist, expose, render, or compile
workflow definitions yet. It is intentionally safe for deployments that do not
enable the workflow designer module.

## Open Questions

- Should workflow definitions be workspace-scoped, agent-scoped, or both?
- Should published workflow versions be immutable by database constraint only,
  or also by API-level policy?
- Should workflow runs reuse `run_id` as the public ID when there is exactly
  one LangGraph run, or expose a separate `workflow_run_id` consistently?
- How much node-pack metadata belongs in Python versus generated TypeScript?
- Should FlowGram be an optional official package or remain a documented
  community adapter until it has enough DeerFlow-specific adoption?
