"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Send } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { isHiddenFromUIMessage } from "@/core/messages/utils";
import { useLocalSettings } from "@/core/settings";
import { useThreadStream } from "@/core/threads/hooks";
import { textOfMessage } from "@/core/threads/utils";
import { uuid } from "@/core/utils/uuid";
import {
  useUpdateWorkUnit,
  workUnitsQueryKey,
  type WorkUnit,
} from "@/core/work-units";

const LEAD_AGENT_NAME = "lead_agent";

function buildWorkUnitPrompt(item: WorkUnit | undefined, userMessage: string) {
  if (!item) return userMessage;
  const fields = [
    ["work_unit_id", item.work_unit_id],
    ["title", item.title],
    ["status", item.status],
    ["priority", item.priority],
    ["assignee_ref", item.assignee_ref ?? ""],
    ["description", item.description ?? ""],
    ["tags", item.labels.join(", ")],
    ["workflow_id", item.workflow_id ?? ""],
    ["thread_id", item.thread_id ?? ""],
    ["run_id", item.run_id ?? ""],
  ]
    .filter(([, value]) => String(value).trim().length > 0)
    .map(([key, value]) => `- ${key}: ${value}`)
    .join("\n");

  return [
    "Work Unit Context",
    fields,
    "",
    "User request",
    userMessage,
    "",
    "Use the Work Unit Context above as the authoritative work record. If the user asks you to execute or continue the work unit, act on this context rather than asking them to paste it again.",
    "If you need to change the Work Unit status, call the work_unit tool first and only claim the change after the tool returns ok=true.",
  ].join("\n");
}

export function WorkUnitChatPanel({
  agents,
  item,
}: {
  agents: Array<{ name: string }>;
  item?: WorkUnit;
}) {
  const [settings] = useLocalSettings();
  const [selectedAgent, setSelectedAgent] = useState(LEAD_AGENT_NAME);
  const [draftThreadId, setDraftThreadId] = useState(() => uuid());
  const [persistedThreadId, setPersistedThreadId] = useState<string | null>(
    item?.thread_id ?? null,
  );
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const updateWorkUnit = useUpdateWorkUnit();
  const queryClient = useQueryClient();

  useEffect(() => {
    const nextAgent =
      item?.assignee_ref && agents.some((agent) => agent.name === item.assignee_ref)
        ? item.assignee_ref
        : LEAD_AGENT_NAME;
    setSelectedAgent(nextAgent);
    setDraftThreadId(uuid());
    setPersistedThreadId(item?.thread_id ?? null);
    setMessage("");
  }, [agents, item?.assignee_ref, item?.thread_id, item?.work_unit_id]);

  const chatContext = useMemo(
    () => ({
      ...settings.context,
      agent_name: selectedAgent === LEAD_AGENT_NAME ? undefined : selectedAgent,
    }),
    [selectedAgent, settings.context],
  );

  const { thread, sendMessage } = useThreadStream({
    threadId: persistedThreadId ?? undefined,
    displayThreadId: draftThreadId,
    context: chatContext,
    onToolEnd: (event) => {
      if (event.name === "work_unit" || event.name === "work_units") {
        void queryClient.invalidateQueries({ queryKey: workUnitsQueryKey });
      }
    },
    onFinish: () => {
      void queryClient.invalidateQueries({ queryKey: workUnitsQueryKey });
    },
    onStart: (createdThreadId) => {
      setPersistedThreadId(createdThreadId);
      if (item && item.thread_id !== createdThreadId) {
        void updateWorkUnit.mutateAsync({
          workUnitId: item.work_unit_id,
          request: { thread_id: createdThreadId },
        });
      }
    },
  });

  const messages = (thread.messages ?? []).filter(
    (chatMessage) => !isHiddenFromUIMessage(chatMessage),
  );
  const chatThreadId = persistedThreadId ?? draftThreadId;
  const chatPath =
    selectedAgent === LEAD_AGENT_NAME
      ? `/workspace/chats/${chatThreadId}`
      : `/workspace/agents/${encodeURIComponent(selectedAgent)}/chats/${chatThreadId}`;

  async function handleSend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = message.trim();
    if (!text || sending || !item) return;
    const promptText = buildWorkUnitPrompt(item, text);
    setSending(true);
    setMessage("");
    try {
      if (!persistedThreadId && !item.thread_id) {
        setPersistedThreadId(chatThreadId);
        await updateWorkUnit.mutateAsync({
          workUnitId: item.work_unit_id,
          request: { thread_id: chatThreadId },
        });
      }
      await sendMessage(
        chatThreadId,
        { text: promptText, files: [] },
        {
          work_unit_id: item?.work_unit_id,
          work_unit_title: item?.title,
          work_unit_status: item?.status,
          work_unit_priority: item?.priority,
          work_unit_description: item?.description,
          work_unit_assignee_ref: item?.assignee_ref,
          source: "workboard",
        },
        {
          additionalKwargs: {
            work_unit_id: item?.work_unit_id,
            work_unit_user_text: text,
            source: "workboard",
          },
        },
      );
    } catch (error) {
      setMessage(text);
      throw error;
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-2 border-b p-3">
        <Select value={selectedAgent} onValueChange={setSelectedAgent}>
          <SelectTrigger aria-label="Agent" className="h-9 min-w-0 flex-1">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {agents.map((agent) => (
              <SelectItem key={agent.name} value={agent.name}>
                {agent.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {persistedThreadId ? (
          <Button asChild variant="outline" size="icon" aria-label="Open full chat">
            <Link href={chatPath}>
              <ExternalLink />
            </Link>
          </Button>
        ) : (
          <Button variant="outline" size="icon" aria-label="Open full chat" disabled>
            <ExternalLink />
          </Button>
        )}
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-2 p-3">
          {messages.length === 0 ? (
            <div className="text-muted-foreground rounded-md border border-dashed p-3 text-sm">
              Start a chat about this work unit.
            </div>
          ) : (
            messages.map((chatMessage, index) => {
              const isHuman = chatMessage.type === "human";
              const userText = Reflect.get(
                chatMessage.additional_kwargs ?? {},
                "work_unit_user_text",
              );
              const text =
                isHuman && typeof userText === "string"
                  ? userText
                  : textOfMessage(chatMessage);
              if (!text) return null;
              return (
                <div
                  key={chatMessage.id ?? index}
                  className={`rounded-md border p-2 text-sm ${
                    isHuman ? "bg-muted/30 ml-6" : "bg-background mr-6"
                  }`}
                >
                  <div className="text-muted-foreground mb-1 text-[10px] font-semibold uppercase">
                    {isHuman ? "You" : selectedAgent}
                  </div>
                  <div className="whitespace-pre-wrap leading-relaxed">{text}</div>
                </div>
              );
            })
          )}
        </div>
      </ScrollArea>
      <form className="grid gap-2 border-t p-3" onSubmit={(event) => void handleSend(event)}>
        <Textarea
          className="min-h-20 resize-none"
          placeholder="Message the agent about this work unit"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          onKeyDown={(event) => {
            if (
              event.key !== "Enter" ||
              event.shiftKey ||
              event.nativeEvent.isComposing
            ) {
              return;
            }
            event.preventDefault();
            event.currentTarget.form?.requestSubmit();
          }}
        />
        <Button type="submit" disabled={sending || !message.trim()}>
          <Send />
          Send
        </Button>
      </form>
    </div>
  );
}
