"use client";

import { useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { useRef, useState } from "react";
import { unwrap, upload } from "@/lib/api";

const KINDS = [
  { id: "order_pad", label: "Orders", hint: "Order pads, emailed orders, scans." },
  { id: "batch_sheet", label: "Batch sheets", hint: "What was made, from which ingredient lots." },
  { id: "haccp_log", label: "HACCP logs", hint: "Temperature and weight checks." },
] as const;
type Kind = (typeof KINDS)[number]["id"];

/** Paper in: drag files, pick files, or take a photo (opens the camera on phones). */
export function Dropzone({ disabled }: { disabled?: boolean }) {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [notes, setNotes] = useState<string[]>([]);
  const [kind, setKind] = useState<Kind>("order_pad");

  async function send(files: FileList | null, source: "upload" | "camera") {
    if (!files?.length) return;
    const out: string[] = [];
    for (const file of Array.from(files)) {
      try {
        const doc = await unwrap(upload({ body: { file, kind, source } }));
        out.push(doc.duplicate ? `${file.name}: already on your desk, not read twice.` : `${file.name}: reading…`);
      } catch (err) {
        out.push(`${file.name}: ${(err as Error).message}`);
      }
    }
    setNotes(out);
    await qc.invalidateQueries({ queryKey: ["documents"] });
    await qc.invalidateQueries({ queryKey: ["dashboard"] });
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        if (!disabled) send(e.dataTransfer.files, "upload");
      }}
      className={clsx(
        "relative overflow-hidden rounded-2xl border-2 border-dashed px-6 py-8 transition-colors",
        over ? "border-inkblue bg-inkblue-soft" : "border-line bg-surface",
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-lg font-semibold tracking-tight">Drop today&apos;s paper here</p>
          <div role="radiogroup" aria-label="What kind of paper" className="mt-2 inline-flex rounded-lg border border-line p-0.5 text-sm">
            {KINDS.map((k) => (
              <button
                key={k.id}
                id={`kind_${k.id}`}
                role="radio"
                aria-checked={kind === k.id}
                onClick={() => setKind(k.id)}
                className={clsx("rounded-md px-3 py-1", kind === k.id ? "bg-ink text-bg" : "text-muted hover:text-ink")}
              >
                {k.label}
              </button>
            ))}
          </div>
          <p className="mt-2 text-sm text-muted">
            {KINDS.find((k) => k.id === kind)?.hint} PDF or photo. Keel reads it, checks it and asks before anything is recorded.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            disabled={disabled}
            onClick={() => cameraRef.current?.click()}
            className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-bg disabled:opacity-50"
          >
            Take a photo
          </button>
          <button
            disabled={disabled}
            onClick={() => fileRef.current?.click()}
            className="rounded-lg border border-line bg-surface px-4 py-2 text-sm font-medium hover:bg-surface-2 disabled:opacity-50"
          >
            Choose files
          </button>
        </div>
      </div>
      <input ref={fileRef} id="file_input" type="file" multiple accept="application/pdf,image/png,image/jpeg,image/webp" hidden onChange={(e) => send(e.target.files, "upload")} />
      <input ref={cameraRef} id="camera_input" type="file" accept="image/*" capture="environment" hidden onChange={(e) => send(e.target.files, "camera")} />
      {notes.length > 0 && (
        <ul className="mt-4 space-y-1 text-sm text-muted">
          {notes.map((n) => <li key={n}>{n}</li>)}
        </ul>
      )}
    </div>
  );
}
