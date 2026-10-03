"use client";

import clsx from "clsx";
import { useEffect, useRef, useState } from "react";

type Step = { name: string; args: Record<string, unknown> };
type Turn = { role: "user" | "keel"; text: string; steps: Step[]; error?: string };

const SUGGESTIONS = [
  "How are we doing today?",
  "Which orders are not invoiced yet?",
  "Best selling products this month",
  "Find mango in the documents",
];

/** Streams Ask Keel (SSE over POST): tokens, tool calls and results as they happen. */
async function* ask(message: string, conversationId: string) {
  const res = await fetch("/api/agent/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ message, conversation_id: conversationId }),
  });
  if (!res.ok || !res.body) throw new Error(`Keel could not answer (${res.status}).`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      if (part.startsWith("data: ")) yield JSON.parse(part.slice(6));
    }
  }
}

export function AskPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [conversationId, setConversationId] = useState(() => crypto.randomUUID());
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);
  useEffect(() => endRef.current?.scrollIntoView({ block: "end" }), [turns]);

  async function send(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    setInput("");
    setBusy(true);
    setTurns((t) => [...t, { role: "user", text: q, steps: [] }, { role: "keel", text: "", steps: [] }]);
    const patch = (fn: (t: Turn) => Turn) => setTurns((all) => [...all.slice(0, -1), fn(all[all.length - 1])]);
    try {
      for await (const ev of ask(q, conversationId)) {
        if (ev.type === "token") patch((t) => ({ ...t, text: t.text + ev.text }));
        if (ev.type === "tool") patch((t) => ({ ...t, steps: [...t.steps, { name: ev.name, args: ev.args }] }));
        if (ev.type === "error") patch((t) => ({ ...t, error: ev.message }));
      }
    } catch (err) {
      patch((t) => ({ ...t, error: (err as Error).message }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div
        className={clsx("fixed inset-0 z-30 bg-ink/20 transition-opacity", open ? "opacity-100" : "pointer-events-none opacity-0")}
        onClick={onClose}
        aria-hidden
      />
      <aside
        aria-label="Ask Keel"
        className={clsx(
          "fixed inset-y-0 right-0 z-40 flex w-full max-w-md flex-col border-l border-line bg-surface shadow-xl transition-transform duration-200",
          open ? "translate-x-0" : "translate-x-full",
        )}
      >
        <header className="flex items-center justify-between border-b border-line px-5 py-4">
          <div>
            <h2 className="font-semibold">Ask Keel</h2>
            <p className="text-xs text-muted">Answers come from your records. Keel can look, not change.</p>
          </div>
          <div className="flex gap-1">
            <button className="rounded-md px-2 py-1 text-xs text-muted hover:bg-surface-2" onClick={() => { setTurns([]); setConversationId(crypto.randomUUID()); }}>
              New
            </button>
            <button className="rounded-md px-2 py-1 text-sm text-muted hover:bg-surface-2" onClick={onClose} aria-label="Close">✕</button>
          </div>
        </header>

        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
          {turns.length === 0 && (
            <div className="space-y-2">
              <p className="text-sm text-muted">Try one of these:</p>
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => send(s)} className="block w-full rounded-lg border border-line px-3 py-2 text-left text-sm hover:border-inkblue">
                  {s}
                </button>
              ))}
            </div>
          )}
          {turns.map((t, i) =>
            t.role === "user" ? (
              <p key={i} className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm bg-ink px-3.5 py-2 text-sm text-bg">{t.text}</p>
            ) : (
              <div key={i} className="space-y-2">
                {t.steps.map((s, j) => (
                  <p key={j} className="num w-fit rounded-md bg-inkblue-soft px-2 py-1 text-xs text-inkblue">
                    looked at {s.name}
                    {Object.keys(s.args).length > 0 && ` ${JSON.stringify(s.args)}`}
                  </p>
                ))}
                {t.text ? (
                  <div className="whitespace-pre-wrap text-sm leading-relaxed">{t.text}</div>
                ) : (
                  !t.error && busy && i === turns.length - 1 && <p className="processing h-4 w-40 rounded" />
                )}
                {t.error && <p className="text-sm text-danger">{t.error}</p>}
              </div>
            ),
          )}
          <div ref={endRef} />
        </div>

        <form
          className="border-t border-line p-4"
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
        >
          <textarea
            id="ask_input"
            ref={inputRef}
            rows={2}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
            placeholder="Ask about orders, invoices, products or paperwork…"
            className="w-full resize-none rounded-lg border border-line bg-surface px-3 py-2 text-sm focus:border-inkblue focus:outline-none"
          />
        </form>
      </aside>
    </>
  );
}
