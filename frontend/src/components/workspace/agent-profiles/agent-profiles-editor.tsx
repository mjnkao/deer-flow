"use client";

import { json } from "@codemirror/lang-json";
import { markdown } from "@codemirror/lang-markdown";
import { python } from "@codemirror/lang-python";
import { yaml } from "@codemirror/lang-yaml";
import { basicLightInit } from "@uiw/codemirror-theme-basic";
import { monokaiInit } from "@uiw/codemirror-theme-monokai";
import CodeMirror from "@uiw/react-codemirror";
import { EditorView } from "codemirror";
import {
  CheckIcon,
  FileCogIcon,
  Loader2Icon,
  RotateCcwIcon,
  SaveIcon,
} from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  getAgentProfileFile,
  getAgentProfileSkills,
  listAgentProfileFiles,
  type AgentProfileFile,
  type AgentProfileFileSummary,
  type AgentProfileSkills,
  updateAgentProfileFile,
  updateAgentProfileSkills,
} from "@/core/agent-profiles/api";
import { enableSkill, loadSkills } from "@/core/skills/api";
import type { Skill } from "@/core/skills/type";
import { cn } from "@/lib/utils";

const customDarkTheme = monokaiInit({
  settings: {
    background: "transparent",
    gutterBackground: "transparent",
    gutterForeground: "#555",
    gutterActiveForeground: "#fff",
    fontSize: "var(--text-sm)",
  },
});

const customLightTheme = basicLightInit({
  settings: {
    background: "transparent",
    fontSize: "var(--text-sm)",
  },
});

function languageExtension(language: AgentProfileFileSummary["language"]) {
  if (language === "json") return json();
  if (language === "python") return python();
  if (language === "yaml") return yaml();
  return markdown();
}

function formatBytes(size?: number | null) {
  if (size == null) return "new";
  if (size < 1024) return `${size} B`;
  return `${Math.round(size / 1024)} KB`;
}

function groupLabel(scope: string) {
  if (scope === "global") return "App config";
  if (scope === "runtime") return "Runtime profile";
  if (scope.startsWith("agent:")) return scope.replace("agent:", "Agent: ");
  if (scope.startsWith("subagent:"))
    return scope.replace("subagent:", "Subagent: ");
  if (scope.startsWith("skills:")) return scope.replace("skills:", "Skills: ");
  return scope;
}

function agentLabel(agentRef: string) {
  if (agentRef === "all") return "All profiles";
  if (agentRef === "global") return "Global runtime";
  if (agentRef === "lead_agent") return "lead_agent";
  if (agentRef.startsWith("subagent:"))
    return agentRef.replace("subagent:", "subagent: ");
  return agentRef;
}

function isSubagentRef(agentRef: string) {
  return agentRef.startsWith("subagent:");
}

function isCustomAgent(agentRef: string) {
  return (
    agentRef !== "all" &&
    agentRef !== "global" &&
    agentRef !== "lead_agent" &&
    !isSubagentRef(agentRef)
  );
}

export function AgentProfilesEditor() {
  const { resolvedTheme } = useTheme();
  const [files, setFiles] = useState<AgentProfileFileSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string>();
  const [selectedFile, setSelectedFile] = useState<AgentProfileFile>();
  const [draft, setDraft] = useState("");
  const [agentFilter, setAgentFilter] = useState("all");
  const [activeTab, setActiveTab] = useState("files");
  const [skills, setSkills] = useState<Skill[]>([]);
  const [skillPolicy, setSkillPolicy] = useState<AgentProfileSkills>();
  const [savingSkill, setSavingSkill] = useState<string>();
  const [loadingFiles, setLoadingFiles] = useState(true);
  const [loadingFile, setLoadingFile] = useState(false);
  const [loadingSkills, setLoadingSkills] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string>();

  const agentOptions = useMemo(() => {
    const refs = new Set<string>(["all", "global", "lead_agent"]);
    for (const file of files) {
      if (file.agent_ref) refs.add(file.agent_ref);
    }
    return Array.from(refs).sort((a, b) => {
      const rank = (value: string) =>
        value === "all"
          ? 0
          : value === "lead_agent"
            ? 1
            : value === "global"
              ? 2
              : 3;
      return rank(a) - rank(b) || a.localeCompare(b);
    });
  }, [files]);

  const selectedAgentRef = agentFilter === "all" ? "lead_agent" : agentFilter;
  const skillPolicyAgentRef = isSubagentRef(selectedAgentRef)
    ? "global"
    : selectedAgentRef;

  const filteredFiles = useMemo(() => {
    if (agentFilter === "all") return files;
    if (agentFilter === "global") {
      return files.filter((file) => file.agent_ref === "global");
    }
    return files.filter(
      (file) => file.agent_ref === "global" || file.agent_ref === agentFilter,
    );
  }, [agentFilter, files]);

  const grouped = useMemo(() => {
    const groups = new Map<string, AgentProfileFileSummary[]>();
    for (const file of filteredFiles) {
      const current = groups.get(file.scope) ?? [];
      current.push(file);
      groups.set(file.scope, current);
    }
    return Array.from(groups.entries());
  }, [filteredFiles]);

  const dirty = Boolean(selectedFile && draft !== selectedFile.content);

  useEffect(() => {
    let cancelled = false;
    setLoadingFiles(true);
    listAgentProfileFiles()
      .then((items) => {
        if (cancelled) return;
        setFiles(items);
        setSelectedId((current) => current ?? items[0]?.id);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingFiles(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (filteredFiles.length === 0) {
      setSelectedId(undefined);
      return;
    }
    if (!selectedId || !filteredFiles.some((file) => file.id === selectedId)) {
      setSelectedId(filteredFiles[0]?.id);
    }
  }, [filteredFiles, selectedId]);

  useEffect(() => {
    if (!selectedId) {
      setSelectedFile(undefined);
      setDraft("");
      return;
    }
    let cancelled = false;
    setLoadingFile(true);
    setError(undefined);
    getAgentProfileFile(selectedId)
      .then((file) => {
        if (cancelled) return;
        setSelectedFile(file);
        setDraft(file.content);
      })
      .catch((err) => {
        if (!cancelled) {
          setSelectedFile(undefined);
          setDraft("");
          setError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingFile(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  useEffect(() => {
    if (activeTab !== "skills") return;
    let cancelled = false;
    setLoadingSkills(true);
    setError(undefined);
    Promise.all([loadSkills(), getAgentProfileSkills(skillPolicyAgentRef)])
      .then(([loadedSkills, policy]) => {
        if (cancelled) return;
        setSkills(loadedSkills);
        setSkillPolicy(policy);
      })
      .catch((err) => {
        if (!cancelled) {
          setSkills([]);
          setSkillPolicy(undefined);
          setError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingSkills(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeTab, selectedAgentRef, skillPolicyAgentRef]);

  async function save() {
    if (!selectedFile || !dirty || saving) return;
    setSaving(true);
    setError(undefined);
    try {
      const saved = await updateAgentProfileFile(selectedFile.id, draft);
      setSelectedFile(saved);
      setDraft(saved.content);
      setFiles((items) =>
        items.map((item) =>
          item.id === saved.id
            ? {
                ...item,
                exists: saved.exists,
                size: saved.size,
                updated_at: saved.updated_at,
              }
            : item,
        ),
      );
      toast.success("Profile file saved");
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
      toast.error(message);
    } finally {
      setSaving(false);
    }
  }

  async function toggleGlobalSkill(skillName: string, enabled: boolean) {
    setSavingSkill(skillName);
    try {
      const updated = (await enableSkill(skillName, enabled)) as Skill;
      setSkills((items) =>
        items.map((item) =>
          item.name === skillName
            ? { ...item, enabled: updated.enabled }
            : item,
        ),
      );
      toast.success(`Global skill ${enabled ? "enabled" : "disabled"}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      toast.error(message);
    } finally {
      setSavingSkill(undefined);
    }
  }

  async function saveCustomSkillPolicy(nextSkills: string[] | null) {
    if (!isCustomAgent(selectedAgentRef)) return;
    setSavingSkill("__policy__");
    try {
      const next = await updateAgentProfileSkills(selectedAgentRef, nextSkills);
      setSkillPolicy(next);
      toast.success("Agent skill policy saved");
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      toast.error(message);
    } finally {
      setSavingSkill(undefined);
    }
  }

  async function toggleCustomSkill(skillName: string, enabled: boolean) {
    if (!skillPolicy || skillPolicy.inherited) return;
    const current = skillPolicy.skills ?? [];
    const next = enabled
      ? Array.from(new Set([...current, skillName]))
      : current.filter((name) => name !== skillName);
    await saveCustomSkillPolicy(next);
  }

  const editorExtensions = useMemo(
    () =>
      selectedFile
        ? [
            languageExtension(selectedFile.language),
            EditorView.lineWrapping,
            EditorView.theme({
              "&": { height: "100%" },
              ".cm-scroller": {
                fontFamily:
                  "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace",
              },
            }),
          ]
        : [],
    [selectedFile],
  );

  return (
    <div className="bg-background flex size-full min-h-0 flex-col">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b px-6 py-4">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold">Agent Profiles</h1>
          <p className="text-muted-foreground mt-0.5 text-sm">
            Edit DeerFlow agent prompts, config files, and skill policies.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {dirty ? (
            <Badge variant="secondary">Unsaved</Badge>
          ) : selectedFile ? (
            <Badge variant="outline">
              <CheckIcon className="size-3" />
              Saved
            </Badge>
          ) : null}
          <Button
            variant="outline"
            disabled={!dirty || saving}
            onClick={() => setDraft(selectedFile?.content ?? "")}
          >
            <RotateCcwIcon />
            Revert
          </Button>
          <Button
            disabled={!dirty || saving || !selectedFile?.editable}
            onClick={save}
          >
            {saving ? <Loader2Icon className="animate-spin" /> : <SaveIcon />}
            Save
          </Button>
        </div>
      </header>

      <Tabs
        value={activeTab}
        onValueChange={setActiveTab}
        className="flex min-h-0 flex-1 flex-col"
      >
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <label className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">
              Agent
            </label>
            <select
              className="bg-background h-9 min-w-56 rounded-md border px-3 text-sm"
              value={agentFilter}
              onChange={(event) => setAgentFilter(event.target.value)}
            >
              {agentOptions.map((agentRef) => (
                <option key={agentRef} value={agentRef}>
                  {agentLabel(agentRef)}
                </option>
              ))}
            </select>
          </div>
          <TabsList>
            <TabsTrigger value="files">Files</TabsTrigger>
            <TabsTrigger value="skills">Skills</TabsTrigger>
            <TabsTrigger value="map">Storage Map</TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="files" className="m-0 min-h-0 flex-1">
          <div className="grid size-full min-h-0 grid-cols-[280px_minmax(0,1fr)]">
            <aside className="bg-muted/20 min-h-0 overflow-y-auto border-r p-3">
              {loadingFiles ? (
                <div className="text-muted-foreground flex h-32 items-center justify-center gap-2 text-sm">
                  <Loader2Icon className="size-4 animate-spin" />
                  Loading profiles
                </div>
              ) : filteredFiles.length === 0 ? (
                <div className="text-muted-foreground p-4 text-sm">
                  No profile files are available for this agent.
                </div>
              ) : (
                <div className="space-y-4">
                  {grouped.map(([scope, items]) => (
                    <section key={scope} className="space-y-1">
                      <div className="text-muted-foreground px-2 text-xs font-semibold tracking-wide uppercase">
                        {groupLabel(scope)}
                      </div>
                      {items.map((file) => (
                        <button
                          key={file.id}
                          className={cn(
                            "hover:bg-accent flex w-full min-w-0 items-start gap-2 rounded-md px-2 py-2 text-left text-sm",
                            selectedId === file.id &&
                              "bg-accent text-accent-foreground",
                          )}
                          type="button"
                          onClick={() => setSelectedId(file.id)}
                        >
                          <FileCogIcon className="mt-0.5 size-4 shrink-0" />
                          <span className="min-w-0 flex-1">
                            <span className="block truncate font-medium">
                              {file.label}
                            </span>
                            <span className="text-muted-foreground mt-0.5 flex gap-2 text-xs">
                              <span>{file.language}</span>
                              <span>{formatBytes(file.size)}</span>
                            </span>
                          </span>
                        </button>
                      ))}
                    </section>
                  ))}
                </div>
              )}
            </aside>

            <main className="flex min-h-0 flex-col">
              {error ? (
                <div className="border-destructive/30 bg-destructive/10 text-destructive border-b px-4 py-2 text-sm">
                  {error}
                </div>
              ) : null}

              <div className="flex items-center justify-between gap-3 border-b px-4 py-3">
                <div className="min-w-0">
                  <div className="truncate font-medium">
                    {selectedFile?.label ?? "Select a profile file"}
                  </div>
                  <div className="text-muted-foreground truncate text-xs">
                    {selectedFile?.path ?? "Choose a file from the left list."}
                  </div>
                </div>
                {selectedFile ? (
                  <div className="flex items-center gap-2">
                    <Badge variant="outline">{selectedFile.language}</Badge>
                    {!selectedFile.editable ? (
                      <Badge variant="secondary">read only</Badge>
                    ) : null}
                  </div>
                ) : null}
              </div>

              <div className="min-h-0 flex-1">
                {loadingFile ? (
                  <div className="text-muted-foreground flex h-full items-center justify-center gap-2 text-sm">
                    <Loader2Icon className="size-4 animate-spin" />
                    Loading file
                  </div>
                ) : selectedFile ? (
                  <CodeMirror
                    value={draft}
                    height="100%"
                    className={cn(
                      "h-full overflow-auto font-mono [&_.cm-editor]:h-full [&_.cm-focused]:outline-none!",
                      "px-2 py-0! [&_.cm-line]:px-2! [&_.cm-line]:py-0!",
                    )}
                    theme={
                      resolvedTheme === "dark"
                        ? customDarkTheme
                        : customLightTheme
                    }
                    extensions={editorExtensions}
                    editable={selectedFile.editable}
                    basicSetup={{
                      foldGutter: true,
                      highlightActiveLine: true,
                      lineNumbers: true,
                    }}
                    onChange={setDraft}
                  />
                ) : (
                  <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
                    Select a profile file.
                  </div>
                )}
              </div>
            </main>
          </div>
        </TabsContent>

        <TabsContent
          value="skills"
          className="m-0 min-h-0 flex-1 overflow-y-auto"
        >
          <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 p-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold">
                  {agentLabel(selectedAgentRef)} skills
                </h2>
                <p className="text-muted-foreground mt-1 text-sm">
                  {selectedAgentRef === "lead_agent"
                    ? "lead_agent reads the globally enabled skills from extensions_config.json."
                    : selectedAgentRef === "global"
                      ? "Global skills are stored in extensions_config.json and are inherited by agents without a whitelist."
                      : "Custom agents store an optional skills whitelist in their config.yaml."}
                </p>
              </div>
              {skillPolicy ? (
                <Badge
                  variant={skillPolicy.inherited ? "outline" : "secondary"}
                >
                  {skillPolicy.inherited
                    ? "inherits global"
                    : "custom whitelist"}
                </Badge>
              ) : null}
            </div>

            {error ? (
              <div className="border-destructive/30 bg-destructive/10 text-destructive rounded-md border px-4 py-2 text-sm">
                {error}
              </div>
            ) : null}

            {loadingSkills ? (
              <div className="text-muted-foreground flex h-32 items-center justify-center gap-2 text-sm">
                <Loader2Icon className="size-4 animate-spin" />
                Loading skills
              </div>
            ) : (
              <>
                {isCustomAgent(selectedAgentRef) ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      variant={skillPolicy?.inherited ? "default" : "outline"}
                      disabled={savingSkill === "__policy__"}
                      onClick={() => saveCustomSkillPolicy(null)}
                    >
                      Inherit global skills
                    </Button>
                    <Button
                      variant={!skillPolicy?.inherited ? "default" : "outline"}
                      disabled={savingSkill === "__policy__"}
                      onClick={() =>
                        saveCustomSkillPolicy(
                          skills
                            .filter((skill) => skill.enabled)
                            .map((skill) => skill.name),
                        )
                      }
                    >
                      Use custom whitelist
                    </Button>
                  </div>
                ) : null}

                <div className="divide-border overflow-hidden rounded-md border">
                  {skills.length === 0 ? (
                    <div className="text-muted-foreground p-4 text-sm">
                      No skills are available.
                    </div>
                  ) : (
                    skills.map((skill) => {
                      const checked = isCustomAgent(selectedAgentRef)
                        ? (skillPolicy?.skills ?? []).includes(skill.name)
                        : skill.enabled;
                      const disabled =
                        savingSkill === skill.name ||
                        savingSkill === "__policy__" ||
                        (isCustomAgent(selectedAgentRef) &&
                          Boolean(skillPolicy?.inherited));
                      return (
                        <div
                          key={skill.name}
                          className="flex items-start justify-between gap-4 border-b p-4 last:border-b-0"
                        >
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-medium">{skill.name}</span>
                              <Badge variant="outline">{skill.category}</Badge>
                              {!skill.enabled &&
                              isCustomAgent(selectedAgentRef) ? (
                                <Badge variant="secondary">
                                  globally disabled
                                </Badge>
                              ) : null}
                            </div>
                            <p className="text-muted-foreground mt-1 text-sm">
                              {skill.description || "No description."}
                            </p>
                          </div>
                          <Switch
                            checked={checked}
                            disabled={disabled}
                            onCheckedChange={(next) =>
                              isCustomAgent(selectedAgentRef)
                                ? toggleCustomSkill(skill.name, next)
                                : toggleGlobalSkill(skill.name, next)
                            }
                          />
                        </div>
                      );
                    })
                  )}
                </div>

                {skillPolicy ? (
                  <div className="text-muted-foreground text-xs">
                    Source: {skillPolicy.source}
                  </div>
                ) : null}
              </>
            )}
          </div>
        </TabsContent>

        <TabsContent value="map" className="m-0 min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-5xl space-y-6 p-6 text-sm">
            <section className="space-y-2">
              <h2 className="text-lg font-semibold">
                Where DeerFlow Stores Agents
              </h2>
              <p className="text-muted-foreground">
                lead_agent is the built-in orchestrator. Its base prompt is
                source code, while runtime overlays live in the DeerFlow home
                directory.
              </p>
              <div className="font-mono text-xs leading-6">
                <div>
                  backend/packages/harness/deerflow/agents/lead_agent/prompt.py
                </div>
                <div>{"{DEER_FLOW_HOME}"}/SOUL.md</div>
                <div>{"{DEER_FLOW_HOME}"}/USER.md</div>
                <div>config.yaml</div>
                <div>extensions_config.json</div>
              </div>
            </section>

            <section className="space-y-2">
              <h3 className="font-semibold">Custom agents</h3>
              <p className="text-muted-foreground">
                New custom agents are isolated by user and are editable here.
                Legacy shared agents are shown read-only until migrated.
              </p>
              <div className="font-mono text-xs leading-6">
                <div>
                  {"{DEER_FLOW_HOME}"}/users/{"{user_id}"}/agents/
                  {"{agent_name}"}/SOUL.md
                </div>
                <div>
                  {"{DEER_FLOW_HOME}"}/users/{"{user_id}"}/agents/
                  {"{agent_name}"}/config.yaml
                </div>
                <div>
                  {"{DEER_FLOW_HOME}"}/users/{"{user_id}"}/agents/
                  {"{agent_name}"}/memory.json
                </div>
                <div>
                  {"{DEER_FLOW_HOME}"}/agents/{"{agent_name}"}/... legacy
                  fallback
                </div>
              </div>
            </section>

            <section className="space-y-2">
              <h3 className="font-semibold">Skill policy</h3>
              <p className="text-muted-foreground">
                Global enabled/disabled skill state lives in
                extensions_config.json. Custom agents can add a skills field in
                config.yaml. Missing skills means inherit all globally enabled
                skills, an empty list means no skills, and a named list means a
                whitelist.
              </p>
            </section>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
