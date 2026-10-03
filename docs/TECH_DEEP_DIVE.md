# Keel technical deep-dive: parsing, models, retrieval, graph and hosting

**Date:** 3 October 2026. **Companion to:** [PROPOSAL.md](PROPOSAL.md).

**Questions answered**
1. Is your Gemini parser cheaper on Gemini 3.8 Flash or GPT-6 Luna?
2. Can we run locally, then on GCP? Can small models run on Cloud Run?
3. Is there something better or cheaper than the Gemini File Search store?
4. Can LandingAI ADE Gen2 or LiteParse read handwriting?
5. Should the semantic layer use Neo4j with GraphRAG and neocarta?

> **How reliable these numbers are.** The network proxy blocked most vendor pricing pages (openai.com, ai.google.dev, landing.ai, neo4j.com). Most prices come from search snippets and third-party sites. **[U]** marks a figure we could not confirm on a primary source. The Luna-versus-Gemini comparison depends most on two of them: Luna's image-token multiplier and Gemini's thinking-token count. Check both with a one-page `usage` call on each API before you commit.

---

## 0. Recommendations at a glance

| Question | Recommendation |
|---|---|
| Gemini 3.8 Flash or GPT-6 Luna for parsing? | **Luna is about 7–14× cheaper per page.** Luna batch costs about $0.37 per 1k pages; Gemini batch about $2.60 now and **$5.20 from 1 Jan 2027**. Quality on handwriting is unproven for Luna, so **don't switch blind**: run both on your gold set. Use Luna (`reasoning.effort=none`, Batch) for printed scans and structured extraction. Keep Gemini 3.8 Flash (thinking LOW) for handwriting until Luna proves itself. |
| Your `gemini_parse_util.py` | Fix 8 things before you change models (§1.3). Thinking is billed by default; there is no per-page splitting, no `media_resolution`, no structured output and no usage logging. Several of these cut cost more than switching models does. |
| Local, then GCP? Small models on Cloud Run? | **Yes.** Locally, use docker-compose with Postgres + pgvector, and Ollama or MLX running GLM-OCR or PaddleOCR-VL (they need about 2–3 GB RAM). On GCP, use Cloud Run for the app, Cloud SQL and GCS. Cloud Run **supports GPUs**: L4 at about $1.05/hr all-in, scaling to zero, and also available for **jobs**. **But at SMB volume, API batch pricing is about as cheap as a fully used L4**, so self-host only for data sovereignty or high steady volume. |
| Gemini File Search store? | **Move to Postgres** (pgvector + pg_textsearch BM25 on Cloud SQL, protected by row-level security). File Search is cheap ($0.15 per 1M indexing tokens, free storage). But your **one store per organisation will hit the reported 10-stores-per-project cap** [U]. Tenant isolation would then rest on a metadata filter, the index cannot be exported, and there is no region pinning. For invoices, **extract to SQL first**, and use vectors only for free text. |
| ADE Gen2 or LiteParse for handwriting? | **LiteParse: no.** It bundles Tesseract, which cannot read cursive; LlamaIndex itself says to use LlamaParse for handwriting. Use LiteParse only to triage born-digital PDFs. **ADE Gen2 (DPT-3 Pro): plausible, unproven.** It claims handwriting support, gives grounding and zero data retention, and costs about 2–3¢ per page (about half on the async tier). There is no independent handwriting benchmark, so test it on 50–100 of your own pages. |
| Neo4j + neocarta for the semantic layer? | **Not now.** neocarta is a *metadata catalog for text-to-SQL*, not a store for tenant data. It is experimental (v0.8.1, Labs) and has no tenancy. Also, **Apache AGE is not available on Cloud SQL**, so the proposal now uses Postgres edge tables with recursive CTEs. Keep the metrics YAML **OSI-compatible** (Open Semantic Interchange, the format neocarta reads) and hide graph access behind an interface. Add Neo4j later as a projection if graph-native needs appear (§5.5). |

---

## 1. Your Gemini parser: Gemini 3.8 Flash vs GPT-6 Luna

### 1.1 Prices (USD per 1M tokens)

| | Gemini 3.8 Flash (intro, to 31 Dec 2026) | Gemini 3.8 Flash (from 1 Jan 2027) | GPT-6 Luna | GPT-6 Luna Batch/Flex |
|---|---|---|---|---|
| Input | $0.75 | $1.50 | $0.10 | $0.05 |
| Cached input | $0.075 | $0.15 | $0.01 | $0.005 |
| Output (includes thinking/reasoning tokens) | $3.75 | $7.50 | $0.50 | $0.25 |
| Batch | 50% off | 50% off | – | 50% off |

The January doubling of Gemini 3.8 Flash's price is confirmed by several independent sources. Luna's price was itself a cut, down from $0.20/$1.20.

### 1.2 How a page becomes tokens, and cost per page

**Gemini 3.x**
- Images and PDF pages are billed at a fixed `media_resolution`: LOW = 280, MEDIUM = 560 and HIGH = 1,120 tokens per page.
- Google says PDF quality "saturates at MEDIUM".
- **Thinking cannot be turned off on 3.8 Flash.** MINIMAL returns an error; LOW is the floor, and the default is MEDIUM. Thinking tokens are billed as output.
- An independent OCR benchmark found that **HIGH thinking made OCR worse**: character error rate 0.406 at HIGH against 0.298 at LOW.

**GPT-6 Luna**
- Images are billed in 32-px patches multiplied by a model factor. For a scanned A4 page this is about 3,000 tokens at high detail [U]. PDF input is billed as text plus an image of each page; whether Luna accepts PDFs directly is unconfirmed [U].
- **`reasoning.effort=none` turns reasoning off completely.**

**Cost per scanned A4 page**, with about 800 tokens of Markdown or JSON output. Gemini at LOW thinking adds about 300 thinking tokens.

| Per page | Standard | Batch | Per 1,000 pages (batch) |
|---|---|---|---|
| Gemini 3.8 Flash, intro price | $0.0046–0.0052 | $0.0023–0.0026 | **≈ $2.60** |
| Gemini 3.8 Flash, 2027 price | $0.0091–0.0104 | $0.0046–0.0052 | **≈ $5.20** |
| GPT-6 Luna, effort `none` | $0.0005–0.0007 | $0.0002–0.0004 | **≈ $0.37** |
| GPT-6 Luna, effort `low` | $0.0006–0.0009 | $0.0003–0.00045 | ≈ $0.45 |

**Output tokens make up 80–90% of the cost on both models.** The cheapest lever is to output less: emit a schema-bound JSON object instead of full Markdown wherever you only need fields.

**Quality evidence (thin)**
- Gemini 3 Flash ranks #2 on OCR Arena (Elo 1784). On socOCRbench, Gemini 3 Flash scored only 0.52–0.64 on handwriting sets.
- There are no public OCR benchmarks for GPT-6 Luna. Its predecessor beat Gemini 3.6 Flash on one OCR test (90.7% vs 88.2%).
- **An image-encoding bug degraded GPT-6 vision until 25 Sep 2026.** Ignore any Luna evaluation run before that date.
- Artificial Analysis Intelligence Index: Gemini 3.8 Flash 41, Luna 33.

**Verdict.** Use Luna for printed scans and extraction to a schema. Keep Gemini for handwriting until your gold-set evaluation says otherwise. Behind the router, this is a configuration change, not a rewrite.

### 1.3 Review of `src/rag/gemini_parse_util.py`

| # | Issue in the current code | Impact | Fix |
|---|---|---|---|
| 1 | No `thinking_config`. Gemini 3.8 Flash defaults to **MEDIUM** thinking, billed as output. Your `gemini_file_store.py` already sets `GEMINI_THINKING_LEVEL=LOW`, but the parser doesn't. | Pays for extra output tokens and slightly *worse* OCR | Set `thinking_level=LOW` |
| 2 | No `media_resolution` | Pays HIGH-resolution token counts where MEDIUM is enough, or the reverse on handwriting | MEDIUM for PDFs; HIGH only for handwriting or photos, set per part |
| 3 | The **whole multi-page document goes in one call** | Long PDFs hit the output-token limit and get truncated silently. There are no per-page retries, no per-page caching and no per-page routing to cheaper tiers. | Split into pages, run in parallel with a semaphore, cache by page hash, and route each page separately (text layer, then OCR, then VLM) |
| 4 | Free-form Markdown output only | No fields, confidence or page references, so nothing to validate. More output tokens too. | Two modes: `response_schema` JSON for extraction (per-field page and quote), and Markdown only for RAG text |
| 5 | `temperature=0.1` | Google's Gemini 3 guidance is to keep the default of 1.0; lower values can cause looping or worse output [U] | Remove it and control output with the schema instead |
| 6 | No usage logging | You can't see cost per page or per tenant | Log `usage_metadata` per call (prompt, candidates, `thoughts_token_count`), with tenant and document IDs |
| 7 | No Batch API | Pays double for inbox work that isn't urgent | Use the Batch API (50% off) for the nightly or async inbox |
| 8 | Upload, then delete, through the Files API on every call; sync wrapper uses `nest_asyncio` | Extra round-trips; fragile in event loops | Send inline bytes for files under about 20 MB; use the native `client.aio` async API |

Two smaller points:
- The docstrings still say gemini-2.0-flash and 2.5-pro.
- The "high" path uses `gemini-3-pro-preview`, which is expensive. Escalate per *field* (ADE, or Gemini 3.1 Pro on a cropped region) rather than re-parsing whole documents.

**A target interface for Keel**

```python
parse_page(page: PageImage, mode: Literal["markdown","extract"], schema: type[BaseModel] | None,
           tier: Literal["auto","t1","t2","t3","t4"]) -> PageResult  # fields, bbox?, confidence, usage, provider
```

Providers sit behind one interface: Gemini, OpenAI Luna, ADE, local GLM-OCR/PaddleOCR-VL, and LiteParse. Routing and escalation follow PROPOSAL §4.4.

---

## 2. Running locally, then on GCP

### 2.1 Local development stack

| Component | Local |
|---|---|
| Postgres 17 + pgvector (+ pg_textsearch if the image has it, else `tsvector`) | `docker-compose` |
| API and agents (FastAPI, deepagents, LangGraph) | `uv run` / container |
| Next.js | `pnpm dev` |
| Object storage | MinIO, or the local filesystem behind a `Storage` interface (you already have `src.storage`) |
| OCR models | **GLM-OCR 0.9B on Ollama** (about 2.2 GB download, 2.5 GB RAM, runs on any Mac with 8 GB or more). **PaddleOCR-VL on MLX**: about 1.3 s per page on an M4 Max, 1.7 GB peak. olmOCR-2 7B needs about 17 GB VRAM at FP16, or 5 GB or more quantized. |
| Sandbox | Docker (from recon v2) |

### 2.2 Production on GCP

| Component | GCP service |
|---|---|
| API, web, workers | **Cloud Run** services |
| Batch OCR and nightly runs | **Cloud Run jobs** (no idle cost) |
| Database | **Cloud SQL for PostgreSQL** (pgvector 0.8.x; pg_textsearch BM25 has been in public preview since 21 Sep 2026). Move to AlloyDB only at scale. |
| Blobs | GCS (per-tenant prefixes, CMEK if needed) |
| Secrets | Secret Manager |
| Queue | Postgres table / pgmq-style, or Cloud Tasks |

### 2.3 Can small models run on Cloud Run? Yes, with GPUs

| | NVIDIA L4 | RTX PRO 6000 (GA Apr 2026) |
|---|---|---|
| VRAM | 24 GB | 96 GB |
| Minimum CPU / RAM | 4 vCPU / 16 GiB | 20 vCPU / 80 GiB |
| All-in price at the minimum shape | **≈ $1.05/hr** | ≈ $3.2/hr |
| Scale to zero | Yes (instance-based billing while it is up) | Yes |
| Cold start | Small models about 10–20 s; large vLLM weights take minutes | – |
| Works for | Services, **jobs** and worker pools | Same |

**Throughput and break-even**
- GLM-OCR does about 1.9 pages/s on vLLM (A100 class). Expect roughly **0.5–1 page/s on an L4** [U].
- That works out to **$0.0003–0.0006 per page only while the GPU is kept busy**.
- GPT-6 Luna batch costs about $0.0003–0.0004 per page with no operations work.
- **So at SMB volumes the API wins.** Self-host only when one of these is true:
  1. a customer requires data residency or sovereignty;
  2. you have a steady load of thousands of pages per hour;
  3. you need a model the APIs don't offer, such as Qwen3-VL-8B for handwriting.

**CPU-only Cloud Run**
- Tesseract runs at about 0.5 s per page and PP-OCRv5 mobile at about 1.75 s per image. That is about $0.00004 per page.
- This is fine for triage and printed text, but weak on handwriting and gives no structure.
- PaddleOCR-VL has no official CPU support.

---

## 3. Gemini File Search vs better and cheaper options

### 3.1 What File Search really costs and limits

| Item | Finding |
|---|---|
| Indexing | $0.15 per 1M tokens, once |
| Storage and query embeddings | Free |
| Retrieved chunks | Billed as input tokens on every query (about 2–5k) |
| Stores per project | **10** [U, stated in several tutorials] |
| Size | Up to 1 TB on Tier 3; keep each store under 20 GB |
| Metadata filtering | Yes (AIP-160 filter syntax), which your code uses |
| Citations | Yes. A reported bug drops citations on Gemini 3 when File Search is combined with function tools (pydantic-ai issue #6207). |
| Residency | No region pinning on the Developer API |
| Lock-in | High: chunks and embeddings cannot be exported |

**Impact on your `gemini_file_store.py`**
- Its design is "one store per organisation" (`<org>_file_search_store`). With a 10-store cap, that **stops working at the 10th tenant**.
- The fallback is one shared store filtered by `organization_id` metadata. Then isolation depends on every query remembering the filter, which is exactly what the proposal's row-level security avoids.

### 3.2 Recommended replacement (all on Cloud SQL)

```
documents / pages / fields (structured extraction)  ← primary path for invoices: SQL + exact match
chunks(tenant_id, doc_id, page, text, tsv, embedding halfvec(768))  ← free text (contracts, notes, SOPs)
  + RLS on tenant_id
  + pgvector HNSW (halfvec; binary_quantize + re-rank at scale; iterative scans for filtered queries)
  + pg_textsearch BM25 (or tsvector) → hybrid via RRF
```

**Embeddings**
- **gemini-embedding-001**, batch: $0.075 per 1M tokens, truncated to 768 dimensions.
- **EmbeddingGemma-300M** or **Qwen3-Embedding-0.6B** self-hosted on CPU: free, and keeps data in-house.

**Why this beats File Search**
- Tenant isolation is enforced by the database.
- One database serves the ledger, the graph and retrieval.
- Exact identifiers (invoice numbers, SKUs, lot numbers) are found by BM25 and SQL, whereas embeddings handle them badly.
- No lock-in, and you control the region.

**Cost model: 100 tenants × 5,000 pages** (500k pages, about 300M tokens, about 750k chunks)

| | Gemini File Search | Postgres + gemini-embedding (batch) | Postgres + EmbeddingGemma on CPU |
|---|---|---|---|
| One-off indexing | $45 | $22.50 | ≈ $5–15 of VM time |
| Storage | Free (2–3 GB of quota) | ≈ 3 GB inside the existing database | ≈ 2 GB |
| Per query | Retrieved tokens + generation | ≈ $0.000002 + generation | ≈ $0 + generation |
| Re-chunking | Pay again | Re-embed | Free |

Indexing cost is trivial on every option. The deciding factors are isolation, lock-in, residency and the number of context tokens per query.

**Retrieval without vectors (agentic search).** For long structured documents (contracts, manuals, SOPs), an agent that reads a table of contents, uses grep or a PageIndex-style tree, or opens pages directly often beats vector RAG. This is how coding agents search, and it fits the deepagents filesystem. For invoices, use SQL. Use vectors as a fallback for free text.

---

## 4. Handwriting: LandingAI ADE Gen2 vs LiteParse vs open models

### 4.1 LiteParse (LlamaIndex): no handwriting

- LiteParse extracts the text layer with PDFium at about 2–5 ms per page, and runs OCR **only** on pages that have no text layer.
- It bundles **Tesseract**, which **cannot read cursive**. You can plug in a PaddleOCR or EasyOCR server, which is only partly better.
- LlamaIndex's own documentation says that for handwriting or scans you will get "significantly better results with **LlamaParse**":
  - Agentic tier: 10 credits ≈ $0.0125 per page
  - Agentic Plus: ≈ $0.056 per page
- LiteParse "v2" is a speed rewrite with no handwriting model.
- **Use it for tier 0 only:** a free text layer for born-digital PDFs.

### 4.2 LandingAI ADE Gen2 (launched about 9 Sep 2026)

| | DPT-3 Pro (default) | DPT-3 Verity |
|---|---|---|
| For | Scans, **handwriting**, non-Latin scripts, math | Born-digital PDFs; deterministic |
| Grounding | Line-level boxes | Word-level boxes with **confidence per word** |
| Price (priority tier) | 1 credit per page + 0.5 per 1k output characters ≈ **$0.02–0.03 per page** | 0.3 credits per page + 0.2 per 1k characters |
| Standard (async) tier | **0.5×** the priority price | Under $0.01 per page |

- **APIs:** Parse, **Extract** (JSON schema with grounding), Split, Classify, Section. Python SDK: `landingai-ade`.
- **Enterprise:** zero data retention; VPC container on AWS, Azure or **GCP**; on-prem.
- **Evidence:** the published DocVQA score is 99.16%, but that was on DPT-2 and printed text. **No independent handwriting benchmark exists for DPT-3.**
- **Use it** as the tier-4 escalation for critical handwritten fields, *if* it passes your gold set.
- Its grounding is the strongest feature: it provides the pixel-level evidence the proposal is built on, which Gemini and Luna don't reliably give.

### 4.3 Open-source handwriting models (for self-hosting or sovereignty)

| Model | Size | Handwriting evidence |
|---|---|---|
| **Qwen3-VL-8B** | 8B, Apache-2.0 | **Best open model** on OmniHandwritingOCR (F1 81.6) and WildHandBench (62.2%) |
| Chandra OCR 2 | 4B | Top downloadable model on olmOCR-bench (≈ 85.9); marketed for handwriting and forms; licence has revenue limits [U] |
| Nanonets-OCR2-3B | 3B | Best specialised model on OmniHandwritingOCR multi-line |
| PaddleOCR-VL-1.6 | 0.9B | #1 on OmniDocBench (96.3) for **printed** documents, but only 54% on WildHandBench |
| GLM-OCR | 0.9B | 95.2 on OmniDocBench; no handwriting data |

**WildHandBench reality check**
- The best system is **Gemini 3.1 Pro at 71.9%, below the human baseline of 77.1%**.
- **63–91% of model errors are "prior-driven"**: the model writes plausible text instead of what is actually written. For invoice amounts this is dangerous.
- So the proposal's rule stands: **no handwritten amount posts without a match from a second source or a human tap.**

---

## 5. Neo4j, GraphRAG and neocarta

### 5.1 What neocarta is

- "An end-to-end library for building a **semantic layer in Neo4j**." It extracts **metadata** from data sources into a graph:
  - `Database → Schema → Table → Column → Value`
  - foreign keys
  - business glossary
  - query logs
  - **OSI metrics**
- It serves that graph to agents through an **MCP server**. Tools include `list_schemas`, hybrid table and column search, `list_metrics_by_domain` and `get_metric_expression`.
- Purpose: **text-to-SQL and data discovery.** "Your data stays in the source."
- Connectors: BigQuery, Dataplex, Snowflake, Databricks, JDBC, CSV and query logs. **OSI YAML import and export.**
- Maturity:
  - v0.8.1, "Experimental", Neo4j Labs (not a Neo4j product)
  - about 142 stars, Apache-2.0
  - a 1.0 refactor is in progress
- **No tenant concept.** Hard dependencies on BigQuery and Dataplex.

**Fit with Keel**
- neocarta could hold the **platform-wide semantic catalog** (metric definitions and table descriptions) so agents can discover metrics.
- It does **not** hold the tenant context graph (vendor, invoice, PO, lot, staff, certification) or agent trace memory.
- The catalog is one shared, non-tenant model, which is small. A few Postgres tables plus pgvector hold it equally well.

### 5.2 Why the proposal had to change: AGE is not on Cloud SQL

**Apache AGE is not offered on Cloud SQL, AlloyDB, RDS/Aurora or Supabase.** It is available on Azure Postgres and EDB. On GCP, using AGE means running Postgres yourself, which removes the "one managed database" benefit.

**New design**
- Typed tables plus a generic `edges(tenant_id, src_type, src_id, rel, dst_type, dst_id, valid_from, valid_to, provenance)` table.
- Recursive CTEs for 1–4 hop traversals, for example lot → supplier → invoice → certificate.
- Row-level security on every table, and pgvector alongside.
- At SMB scale (thousands to low millions of edges per tenant) this is fast enough.

### 5.3 Neo4j options and monthly cost [U]

| Option | Cost | Tenant isolation | Ops |
|---|---|---|---|
| Cloud SQL edge tables (already needed) | **+$0** | RLS (strong) | Lowest |
| Aura Professional, shared graph, 4–8 GB | ≈ $260–520 | `tenantId` checks in application code only | Low, but two databases to keep in sync |
| Aura Business Critical (multiple databases, RBAC), 8 GB | ≈ $1,170+ | Database per tenant | Medium |
| Aura instance per tenant | ≥ $65 × N | Strong | Poor |
| Neo4j Community on a Compute Engine VM | ≈ $50–120 | Application-level only; **one database, no RBAC**, GPLv3 | Medium-high |
| Neo4j Enterprise via the **Startup Program** (free licence if under 50 staff and under $3M revenue) on GKE | ≈ $300–600 of infrastructure | Database per tenant | High |
| Spanner Graph (GCP) | ≈ $30–900 | Key scoping | Low-medium |
| FalkorDB Cloud (graph per tenant natively; SSPL licence) | ≈ $73–350 | Native | Low |

**Note.** Neo4j's full-text and vector index results **bypass per-entry security**, so tenant filters must always be applied. Giving agents a raw Cypher MCP tool (`mcp-neo4j-cypher`) in a multi-tenant system is risky.

### 5.4 GraphRAG frameworks: build the graph deterministically

- Microsoft GraphRAG and LightRAG build the graph with an LLM. Indexing about 500 pages costs about $50–200 at older GPT-4 prices; LightRAG is about 100× cheaper [U].
- `neo4j-graphrag`'s `SimpleKGPipeline` also extracts with an LLM.
- **Keel already extracts schema-validated fields.** Building the graph is therefore deterministic `INSERT`/`MERGE` from validated extraction. It is cheaper, auditable and repeatable.
- Use LLM graph extraction only for free text such as contract obligations, and even there extract into a fixed schema.
- **Graphiti (Zep)**, a temporal agent-memory graph, is attractive. But it needs Neo4j or FalkorDB (no Postgres backend) and calls the LLM on every episode. Revisit it if trace memory outgrows the Postgres trace tables.

### 5.5 When Neo4j becomes worth it

Adopt Neo4j as a **projection** only when one of these appears:
1. 5+ hop or variable-length traversals, such as multi-tier lot genealogy or fraud rings across vendors;
2. graph algorithms such as centrality or community detection;
3. you want Graphiti temporal memory;
4. analysts or agents really benefit from text-to-Cypher;
5. a customer asks for it.

Postgres stays the source of truth, and change data capture (CDC) feeds the projection. Use Aura Professional through GCP Marketplace, or the Startup-licence Enterprise edition for a database per tenant. Your `edm_sementic_layer_v3.0` Neo4j skills carry straight over.

### 5.6 Can we run Neo4j in Docker and deploy it to Cloud Run?

**Locally:** yes. `docker run neo4j:5` in docker-compose is the right way to develop and test the Neo4j path.

**On Cloud Run, the container starts, but it is the wrong place for a database.**

| Issue | Why it matters on Cloud Run |
|---|---|
| **Storage is temporary** | The container's writable filesystem lives in memory. It is lost whenever an instance is replaced (redeploy, scale to zero, maintenance), so the graph disappears unless you mount a volume. |
| **Mountable volumes don't suit databases** | Cloud Storage FUSE has no proper file locking and slow random writes, which risks store corruption. NFS (Filestore) works technically, but Neo4j advises against network filesystems, and Filestore Basic starts at 1 TiB (about $160–200 a month) [U]. |
| **Only one instance is safe** | Two instances would each hold their own copy of the graph. You must set `max-instances=1`, so there is no HA and no scaling. |
| **The driver can't connect through Cloud Run ingress** | Cloud Run ingress accepts HTTP/1, HTTP/2, gRPC and WebSockets on one port. The Python driver speaks **Bolt over raw TCP (7687)**, so it cannot reach the database through Cloud Run's front door. You would be limited to Neo4j's HTTP Query API and would lose the driver's features. |
| **It is always on and slow to start** | Scale-to-zero means JVM cold starts and page-cache warm-up on the first query. To avoid that you set `min-instances=1` with always-allocated CPU, which costs about $60–100 a month for 2 vCPU / 8 GiB [U]. That is more than a VM that does the job properly. |
| **No backups** | You would have to write your own dump-to-GCS job. Community Edition has no online backup [U]. |

**The same container works fine on GCP this way:**

- **Compute Engine VM** (Container-Optimized OS) running the same `neo4j:5` image, with a **persistent disk** and scheduled snapshots.
  - Sizing: e2-medium, about $25 a month, for dev or small use; e2-standard-2, about $50 a month, for production.
  - Cloud Run services connect over Bolt to the VM's **private IP** using Direct VPC egress. Nothing is exposed publicly.
- **GKE Autopilot** with a StatefulSet and a persistent volume, using Neo4j's Helm chart. Choose this if you are already on GKE.
- **Aura Professional through GCP Marketplace**, if you would rather pay about $65 per GB-month than run it yourself.

**Recommendation.**
- Docker locally for experiments.
- If we adopt the Neo4j projection (§5.5), run it on a small Compute Engine VM next to Cloud SQL, not on Cloud Run.
- Postgres stays the system of record. Neo4j holds a projection that can be rebuilt from Postgres at any time, which lowers the backup risk.

**Do now**
1. Keep the governed-metrics YAML **OSI-compatible**, so neocarta or other OSI tools can consume it later at no cost.
2. Put graph access behind a repository interface (`neighbors`, `trace_lot`, `find_paths`).
3. Swapping the backend later then doesn't touch agents or skills.

---

## 6. Revised document pipeline (with these findings)

| Tier | Engine | Notes |
|---|---|---|
| 0 | LiteParse / PDFium | Born-digital only; free |
| 1 | GLM-OCR or PaddleOCR-VL (Ollama locally; Cloud Run GPU job or GLM-OCR API in the cloud) | Printed scans; boxes |
| 2 | **GPT-6 Luna** (`effort=none`, Batch, JSON schema) | Cheapest structured extraction |
| 3 | **Gemini 3.8 Flash** (thinking LOW, `media_resolution` per part) | Handwriting and low-confidence re-reads |
| 4 | **ADE DPT-3 Pro** (standard tier) or Gemini 3.1 Pro on cropped fields | Grounded evidence for critical fields |
| H | Human review | Mandatory for handwritten amounts without a second-source match |

**Gold-set evaluation, first task.** Score Luna, Gemini 3.8 Flash, ADE DPT-3 Pro, GLM-OCR and Qwen3-VL-8B on 100+ labelled pages, including your handwritten order pads and QC/HACCP sheets. Measure field-level accuracy, cost per page and latency. Let that result set the router thresholds.

---

## Sources

**Models and pricing**
- https://openrouter.ai/openai/gpt-6-luna
- https://www.digitalapplied.com/blog/gemini-3-8-flash-costs-the-same-until-it-doubles-in-january
- https://tokencost.app/blog/gemini-3-8-flash-introductory-price-expiry
- https://ai.google.dev/gemini-api/docs/media-resolution
- https://github.com/luseloso/gemini-thinking-ocr-benchmark
- https://mixed-news.com/en/image-encoding-bug-degraded-gpt-6-sol-luna-rerun-evaluations/
- https://artificialanalysis.ai/models/comparisons/gpt-6-luna-high-vs-gemini-3-8-flash

**Cloud Run**
- https://docs.cloud.google.com/run/docs/configuring/services/gpu
- https://docs.cloud.google.com/run/docs/configuring/jobs/gpu
- https://cloud.google.com/run/pricing
- https://cloud.google.com/blog/topics/developers-practitioners/a-guide-to-ai-cold-starts-on-cloud-run

**Local OCR**
- https://docs.z.ai/guides/vlm/glm-ocr
- https://www.buildwithmatija.com/blog/run-glm-ocr-macbook-ollama
- https://github.com/Lulzx/paddleocr-vl.swift

**File Search and RAG**
- https://ai.google.dev/gemini-api/docs/file-search
- https://www.philschmid.de/gemini-file-search-javascript
- https://github.com/pydantic/pydantic-ai/issues/6207
- https://www.globenewswire.com/news-release/2026/09/21/3365524/0/en/google-cloud-brings-native-bm25-full-text-search-to-alloydb-and-cloud-sql-via-tiger-data-s-pg_textsearch.html
- https://github.com/VectifyAI/PageIndex

**Handwriting**
- https://github.com/run-llama/liteparse
- https://developers.llamaindex.ai/llamaparse/general/pricing/
- https://landing.ai/blog/introducing-agentic-document-extraction-gen2
- https://docs.landing.ai/ade/zdr
- https://arxiv.org/abs/2608.22959
- https://arxiv.org/abs/2608.18586
- https://huggingface.co/datalab-to/chandra-ocr-2

**Graph**
- https://github.com/neo4j-labs/neocarta
- https://neo4j.com/pricing/
- https://neo4j.com/docs/operations-manual/current/authentication-authorization/limitations/
- https://github.com/apache/age/discussions/2305
- https://github.com/orgs/supabase/discussions/40285
- https://help.getzep.com/graphiti/getting-started/overview
- https://www.falkordb.com/plans/
- https://cloud.google.com/spanner/pricing
