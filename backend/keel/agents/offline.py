"""Offline chat model for local use without API keys.

It speaks the tool-calling protocol, so the real deepagents graph (skills, tools, memory, streaming) runs
unchanged. It routes a question to one tool by keywords, then summarises the tool's JSON in plain words.
"""

import json
import re
from collections.abc import Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

ROUTES: list[tuple[str, str, dict[str, Any]]] = [
    (r"\b(order|orders)\b.*\b(not|un)\s*-?invoiced|unbilled", "find_orders", {"status": "approved"}),
    (r"\b(invoice|invoiced|billed)\b", "list_invoices", {}),
    (r"\b(best|top|sell|selling|product|products|revenue by)\b", "sales_by_product", {}),
    (r"\border\s+#?\s*(?P<number>[A-Z]*-?\d+)", "order_details", {}),
    (r"\b(orders?|customer)\b", "find_orders", {}),
    (r"\b(find|search|where|document|paper|page|mention)\b", "search_documents", {}),
    (r"\b(catalog|price|prices|customers)\b", "catalog", {}),
]


def _route(question: str) -> tuple[str, dict[str, Any]]:
    q = question.lower()
    for pattern, name, args in ROUTES:
        m = re.search(pattern, q, re.I)
        if not m:
            continue
        args = dict(args)
        if name == "order_details":
            args["number"] = m.group("number").upper()
        if name == "search_documents":
            args["query"] = (
                re.sub(r"\b(find|search|where|is|the|a|an|for|document|documents|mention|of)\b", " ", q).strip()
                or question
            )
        if name == "find_orders" and (cm := re.search(r"\bfor ([a-z][\w' ]+)", q)):
            args["customer"] = cm.group(1).strip()
        return name, args
    return "business_snapshot", {}


def _summarise(name: str, data: dict[str, Any]) -> str:
    if "error" in data:
        return str(data["error"])
    if name == "business_snapshot":
        cur = data.get("currency") or ""
        return (
            f"Right now: {data['documents_to_review']} document(s) to review, {data['approvals_pending']} "
            f"approval(s) waiting, and {data['orders_not_invoiced']} order(s) not yet invoiced worth "
            f"{cur} {float(data['value_not_invoiced']):,.2f}. Invoiced in the last 30 days: "
            f"{cur} {float(data['invoiced_last_30_days']):,.2f}. AI spend this month: "
            f"USD {float(data['ai_spend_this_month_usd']):.4f}."
        )
    if name == "find_orders":
        if not data["orders"]:
            return "I found no matching orders in that period. That means none were recorded, not that sales were zero."
        rows = "\n".join(
            f"- {o['number']}: {o['customer']}, {o['currency']} {float(o['total']):,.2f} ({o['status']})"
            for o in data["orders"][:10]
        )
        return f"{data['count']} order(s):\n{rows}"
    if name == "order_details":
        rows = "\n".join(
            f"- {ln['qty']} {ln['unit']} {ln['item']} at {ln['unit_price']} = {ln['line_total']}"
            for ln in data["lines"]
        )
        head = f"Order {data['number']} for {data['customer']} ({data['status']})"
        return f"{head}, total {data['currency']} {data['total']}:\n{rows}"
    if name == "sales_by_product":
        if not data["products"]:
            return f"No orders in the last {data['days']} days."
        rows = "\n".join(
            f"- {p['product']}: {float(p['quantity']):g} sold, {float(p['revenue']):,.2f}"
            for p in data["products"][:10]
        )
        return f"Sales by product, last {data['days']} days:\n{rows}"
    if name == "list_invoices":
        if not data["invoices"]:
            return "No invoices issued in that period."
        rows = "\n".join(
            f"- {i['number']}: {i['customer']}, {i['currency']} {float(i['total']):,.2f}, due {i['due_date']}"
            for i in data["invoices"][:10]
        )
        return f"{data['count']} invoice(s):\n{rows}"
    if name == "search_documents":
        if not data["matches"]:
            return "Nothing in the uploaded documents matches that."
        rows = "\n".join(f"- {m['file']}, page {m['page']}: …{m['snippet']}…" for m in data["matches"][:5])
        return f"Found in these documents:\n{rows}"
    if name == "catalog":
        return f"{len(data['products'])} products and {len(data['customers'])} customers. Products: " + ", ".join(
            f"{p['name']} ({p['sku']})" for p in data["products"][:12]
        )
    return json.dumps(data)[:800]


class OfflineModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "keel-offline"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "OfflineModel":
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        last = messages[-1]
        if isinstance(last, ToolMessage):
            try:
                data = json.loads(str(last.content))
            except json.JSONDecodeError:
                data = {"error": str(last.content)}
            text = _summarise(last.name or "", data) + "\n\n_(Offline mode: set OPENAI_API_KEY for full answers.)_"
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])
        question = next((str(m.content) for m in reversed(messages) if isinstance(m, HumanMessage)), "")
        name, args = _route(question)
        msg = AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call_{name}"}])
        return ChatResult(generations=[ChatGeneration(message=msg)])
