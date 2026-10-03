"use client";

import clsx from "clsx";
import type { FieldOut, PageOut } from "@/lib/api";
import { label } from "@/lib/format";

/** The page as photographed, with every extracted value boxed where Keel read it. */
export function PageViewer({
  documentId,
  page,
  fields,
  activeId,
  onSelect,
  lowConfidence = 0.75,
}: {
  documentId: string;
  page: PageOut;
  fields: FieldOut[];
  activeId: string | null;
  onSelect: (id: string) => void;
  lowConfidence?: number;
}) {
  const boxed = fields.filter((f) => f.box && f.box.page_id === page.id);
  return (
    <figure className="relative overflow-hidden rounded-xl border border-line bg-white shadow-sm">
      {/* eslint-disable-next-line @next/next/no-img-element -- authenticated, same-origin page render */}
      <img
        src={`/api/documents/${documentId}/pages/${page.n}/image`}
        alt={`Page ${page.n}`}
        width={page.width}
        height={page.height}
        className="block h-auto w-full select-none"
        draggable={false}
      />
      {boxed.map((f) => {
        const b = f.box!;
        const low = f.status !== "corrected" && f.confidence < lowConfidence;
        const active = f.id === activeId;
        return (
          <button
            key={f.id}
            type="button"
            title={`${label(f.path)}: ${String(f.value ?? "")}`}
            onClick={() => onSelect(f.id)}
            style={{
              left: `${b.x * 100}%`,
              top: `${b.y * 100}%`,
              width: `${Math.max(b.w * 100, 1.2)}%`,
              height: `${Math.max(b.h * 100, 1.2)}%`,
            }}
            className={clsx(
              "absolute -m-0.5 rounded-[3px] border-2 transition-all",
              f.status === "corrected" && "border-ledger bg-ledger/10",
              f.status !== "corrected" && !low && "border-inkblue/70 bg-inkblue/5 hover:bg-inkblue/15",
              low && "attention border-carbon bg-carbon/20",
              active && "z-10 scale-[1.04] border-inkblue bg-inkblue/20 ring-4 ring-inkblue/25",
            )}
          />
        );
      })}
      <figcaption className="absolute bottom-2 right-2 rounded-md bg-ink/75 px-2 py-0.5 text-xs text-bg">
        Page {page.n} · {page.has_text_layer ? "text layer" : "read by OCR"}
      </figcaption>
    </figure>
  );
}
