"use client";

import { BatchApproval } from "@/components/review/BatchApproval";
import { HaccpApproval } from "@/components/review/HaccpApproval";
import { OrderApproval } from "@/components/review/OrderApproval";
import type { ApprovalOut } from "@/lib/api";

const BY_GATE = { create_order: OrderApproval, sign_off_batch: BatchApproval, record_haccp: HaccpApproval };

/** The gate for whatever this document becomes; each kind states exactly what approving will write. */
export function ApprovalCard(props: { approval: ApprovalOut; runId: string; editable: boolean }) {
  const Card = BY_GATE[props.approval.gate as keyof typeof BY_GATE];
  return Card ? <Card {...props} /> : <p className="text-sm text-muted">Unknown approval: {props.approval.gate}</p>;
}
