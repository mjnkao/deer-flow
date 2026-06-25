"use client";

import { json } from "@codemirror/lang-json";
import { markdown } from "@codemirror/lang-markdown";
import { yaml } from "@codemirror/lang-yaml";
import { monokai } from "@uiw/codemirror-theme-monokai";
import CodeMirror from "@uiw/react-codemirror";
import { EditorView } from "codemirror";
import {
  CheckIcon,
  FileCogIcon,
  Loader2Icon,
  RotateCcwIcon,
  SaveIcon,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  getAgentProfileFile,
  listAgentProfileFiles,
  type AgentProfileFile,
  type AgentProfileFileSummary,
  updateAgentProfileFile,
} from "@/core/agent-profiles/api";
import { cn } from "@/lib/utils";

function languageExtension(language: AgentProfileFileSummary["language"]) {
  if (language === "json") return json();
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
  if (scope === "repo") return "Instruction docs";
  if (scope === "runtime") return "Runtime profile";
  if (scope.startsWith("agent:")) return scope.replace("agent:", "Agent: ");
  return scope;
}

export function AgentProfilesEditor() {
  const [files, setFiles] = useState<AgentProfileFileSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string>();
  const [selectedFile, setSelectedFile] = useState<AgentProfileFile>();
  const [draft, setDraft] = useState("");
  const [loadingFiles, setLoadingFiles] = useState(true);
  const [loadingFile, setLoadingFile] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string>();

  const grouped = useMemo(() => {
    const groups = new Map<string, AgentProfileFileSummary[]>();
    for (const file of files) {
      const current = groups.get(file.scope) ?? [];
      current.push(file);
      groups.set(file.scope, current);
    }
    return Array.from(groups.entries());
  }, [files]);

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
    if (!selectedId) return;
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

  const editorExtensions = useMemo(
    () =>
      selectedFile
        ? [
            languageExtension(selectedFile.language),
            EditorView.lineWrapping,
            EditorView.theme({
              "&": { height: "100%" },
              ".cm-scroller": { fontFamily: "var(--font-mono)" },
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
            Edit DeerFlow agent prompts and runtime config files.
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

      <div className="grid min-h-0 flex-1 grid-cols-[280px_minmax(0,1fr)]">
        <aside className="bg-muted/20 min-h-0 overflow-y-auto border-r p-3">
          {loadingFiles ? (
            <div className="text-muted-foreground flex h-32 items-center justify-center gap-2 text-sm">
              <Loader2Icon className="size-4 animate-spin" />
              Loading profiles
            </div>
          ) : files.length === 0 ? (
            <div className="text-muted-foreground p-4 text-sm">
              No profile files are available. Enable agents_api in config.yaml.
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
                theme={monokai}
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
    </div>
  );
}
