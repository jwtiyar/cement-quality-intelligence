# Claude-Mem Memory Context

<claude-mem-context>
# Memory Context from Past Sessions

*No context yet. Complete your first session and context will appear here.*

Use claude-mem search tools for manual memory queries.
</claude-mem-context>

# Global Workflow Rules (apply to every project)

## Commit & Push Gate: React Doctor

- **Run `npx react-doctor@latest` before EVERY commit and before EVERY push.** For
  monorepos, run it at the repo root so it scores every detected React project.
- The score is a hard gate: do not commit or push while the score is dropping or
  while any new finding is introduced.
- After every commit that touched frontend/React code, re-run react-doctor and
  confirm the score is unchanged or improved before pushing.
- If react-doctor reports a finding, fix the underlying code first (do not suppress
  without evidence). Only suppress verified false positives, with an inline
  `// react-doctor-disable-next-line <rule> -- <reason>` comment or a narrow
  `ignore.overrides` entry in the project's `doctor.config.*`.
- Treat react-doctor as the source of truth for the health score; never rely on a
  previously recorded score without re-running the tool.

## Commit & Push Gate: Betterleaks

- **Run `betterleaks git .` (and `betterleaks dir .` for new untracked files) before
  EVERY commit and before EVERY push.** Many projects enforce the same scans in CI
  (`.github/workflows/betterleaks.yml`), so a leak that passes locally still fails
  in CI — run the check yourself first.
- **Zero-leak rule**: a new finding is a hard blocker. Do not commit or push while a
  scan reports leaks.
- If a scan reports a finding, fix the underlying leak first — rotate the secret if
  it's real, remove it from the diff if it shouldn't be there. Never add an ignore
  entry for a real secret.
- **False positives only**: suppress with an entry in the project's `.betterleaksignore`
  (format: `file:rule-id:start-line`) or a `// gitleaks:allow` / `// betterleaks:allow`
  comment on the line. Ignore entries must name a real path + rule — never
  blanket-skip a whole rule. If a project ships a `.betterleaksignore`, respect and
  extend it (build-output artifacts) instead of fighting it.
- **`.env*` files** are gitignored but betterleaks `dir` scans them anyway — keep
  real secrets out of new `.env` files too, and never rename them into a tracked path.
- If betterleaks is not installed, use its container image instead:
  `docker run --rm -v "$PWD":/repo -w /repo ghcr.io/betterleaks/betterleaks:latest git /repo`
  (and the same for `dir`).

<!-- CODEGRAPH_START -->
## CodeGraph

In repositories indexed by CodeGraph (a `.codegraph/` directory exists at the repo root), reach for it BEFORE grep/find or reading files when you need to understand or locate code:

- **MCP tool** (when available): `codegraph_explore` answers most code questions in one call — the relevant symbols' verbatim source plus the call paths between them, including dynamic-dispatch hops grep can't follow. Name a file or symbol in the query to read its current line-numbered source. If it's listed but deferred, load it by name via tool search.
- **Shell** (always works): `codegraph explore "<symbol names or question>"` prints the same output.

If there is no `.codegraph/` directory, skip CodeGraph entirely — indexing is the user's decision.
<!-- CODEGRAPH_END -->

## Tool Navigation Order

Use these in order, but treat grep as the always-available backstop:

1. **grep / glob** — use when you know literal text: symbol spellings, string literals, error messages, fixture values, TODO markers, imports. Code indexes resolve symbols and call paths, not prose, comments, or string data — don't skip grep because an index exists. Use the `grep` tool with `include` patterns to narrow, and Glob to find files by path shape before reading them.
2. **CodeGraph** (above) — resolves symbols, their verbatim source, and cross-file call paths including dynamic-dispatch hops.
3. **Graphify** (below) — answers architecture/relationship questions from a pre-built knowledge graph.
4. **Read** — confirm facts at the line level in the real files once located.

## Graphify

In repositories with a `graphify-out/` directory (a pre-built knowledge graph exists, typically at the repo root), treat it as a peer of CodeGraph for architecture and relationship questions:

- **Query it** before reading files: `graphify query "<question>"` (BFS traversal for broad context; add `--dfs` to trace one path). `graphify explain "<Node>"` explains a single node in plain language; `graphify path "A" "B"` finds the shortest path between two concepts.
- **Mind the freshness**: `graphify-out/GRAPH_REPORT.md` records the commit the graph was built from under `## Graph Freshness`. If `git rev-parse HEAD` has moved past it, the graph is stale for recently changed code — fall back to CodeGraph (live, symbol-level) or grep for anything new, and offer `graphify update .` to refresh.
- **Use the sidecar outputs to get oriented fast**: `GRAPH_REPORT.md` (god nodes, community hubs, surprising connections, suggested questions), `graph.json` (GraphRAG-ready), `graph.html` (interactive viz).
- Graphify reflects the corpus **at build time** — never trust it for exact current code state. Verify line-level facts in the real source before editing.

## Agent skills

### Issue tracker

Work is tracked as local markdown issues under `.scratch/<feature>/` in the repo. See `docs/agents/issue-tracker.md`.

### Triage labels

Custom vocabulary with the `qc:` prefix: `qc:triage`, `qc:needs-info`, `qc:ready-for-agent`, `qc:ready-for-human`, `qc:wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context — `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

# CEMENT QUALITY INTELLIGENCE KNOWLEDGE BASE

## OVERVIEW

**Cement Quality Intelligence** is a laboratory engineering and decision-support system for cement manufacturing plants. It integrates:
1. **Quality Analytics**: Historical laboratory quality monitoring across OPC, SRC, and SBC cement types.
2. **Strength Estimation (ML & Baselines)**: Out-of-time predictive models estimating 28-day mortar prism compressive strength from early 2-day strength, fineness, and oxide chemistry.
3. **Raw Mix Optimization**: F.L. Smidth 4x4 matrix proportion solver balancing Limestone, Shale/Clay, Sand, and Iron Ore/Pyrite to hit target LSF, SM, and AM moduli under HFO fuel combustion conditions.
4. **Plant Operations Assistant & Technical RAG**: Hybrid AI assistant using technical reference standards and plant laboratory data with safety review gating.

---

## ARCHITECTURE & CONCURRENCY CONSTRAINTS

### Single-Worker Deployment
- **CRITICAL CONSTRAINT**: The production server MUST be started as a single process:
  ```bash
  uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1
  ```
- **Rationale**: State synchronization, the transactional data refresh lock (`asyncio.Lock`), and atomic in-memory snapshot switches (`AppStateSnapshot`) are coordinated within the Python process memory space. Running multiple worker processes (`--workers > 1`) would cause split-brain data state and inconsistent cache refreshes unless backed by an external distributed lock and shared cache (e.g. Redis).

### Immutability & Snapshot Semantics
- `AppStateSnapshot` encapsulates the active dataframe, trained models, data cache, and dataset version.
- API requests capture `snapshot = state.get_snapshot()` once at the start of request handling.
- Published snapshot attributes and underlying data structures (`df`, `data_cache`, `xgb_models`) must be treated as strictly read-only.
- Never mutate state in-place. State updates occur only via atomic snapshot swaps.

---

## DATA REFRESH, PROVENANCE & CRASH RECOVERY

### Data Pipelines
- **Raw Sources**: Yearly plant laboratory Excel workbooks spanning 2013–2026.
- **Extraction**: `build_dataset.py` processes raw workbooks into consolidated `ALL_CEMENT_DATA.csv`.
- **Target Extraction**: Consolidates verified equivalent 28-day compressive strength columns (`Cmp.St. Mpa_28 day`, `28 day`, `28 days`) and records column provenance in `Strength_28D_Source`.
- **Early Strength Input**: The model contract strictly requires 2-day strength (`Strength_Early` == `Strength_2D`). 3-day and 7-day values are never mixed into this target.

### Refresh Protection & Atomicity
- **Transactional Staging**: Background extraction builds a candidate file (`ALL_CEMENT_DATA.csv.tmp`).
- **Data Loss Validation**: The candidate must cover expected cement types, year ranges, and workbook integrity. If candidate rows drop unexpectedly without explicit override, `UnexplainedDataLossError` is raised and the active dataset is preserved.
- **Rollback & Backup**: Before replacing the active CSV, the current file is copied to `ALL_CEMENT_DATA.csv.bak`.
- **Atomic Swap**: `os.replace` commits the staging file to `ALL_CEMENT_DATA.csv`.
- **Crash Recovery**: If the server starts and finds `ALL_CEMENT_DATA.csv` missing or empty, it automatically restores from `ALL_CEMENT_DATA.csv.bak`.
- **Decoupled Startup**: If ML training fails during server startup, the server still boots in safe fallback mode. Valid data browsing and the raw mix optimizer remain operational while ML predictions fall back to recent baselines.

---

## MACHINE LEARNING & EVALUATION STANDARDS

### Physical Curing Delay & Availability Cutoffs
- **Physical Reality**: Mortar prism compressive strength tests require a physical 28-day curing incubation period.
- **Prediction Timing**: For a production sample taken on date D_sample, early 2-day testing completes at T_pred = D_sample + 2 days.
- **Leakage Prevention**: Any historical sample used to predict D_sample must have had its 28-day test completed and recorded on or before T_pred. In the absence of recorded test completion timestamps, the physical curing constraint enforces:
  D_train <= D_sample - 26 days
- **Symmetric Baseline**: The recent-mean baseline must respect the identical availability cutoff as the ML model.

### Promotion Gating
To be promoted as an active decision-support model over the historical/recent baseline:
1. **Expanding Folds**: Must be evaluated across >= 3 chronological out-of-time folds without future lookahead.
2. **Win Rate**: The model must outperform the baseline in >= 75% of evaluated folds.
3. **Accuracy Margin**: The model must demonstrate an aggregate out-of-time MAE reduction of >= 5% compared to the recent-mean baseline.
4. **Correlation**: Must achieve R^2 > 0.25 on the validation holdout.
5. **Honest Reporting**: When a model is not promoted, the system transparently falls back to `recent_mean` and reports the true baseline error metrics, never fabricated model statistics.

---

## TYPE-SAFE AI & ASSISTANT PROTOCOL

### Safety Decision Validation
- `/api/chat` strictly validates TypeSafe review responses:
  - `status == "approved"` <=> `enabled == True` and `safe_to_show == True`
  - `status == "rejected"` <=> `enabled == True` and `safe_to_show == False`
  - `status == "not_reviewed"` <=> `enabled == False` and `safe_to_show == None`
- Unreviewed predictions are never assumed approved.

### LLM Execution Safety
- Synchronous LLM calls are offloaded from the event loop using `anyio.to_thread.run_sync`.
- Assistant queries enforce a whole-request timeout of 35 seconds, returning HTTP 504 on deadline expiration.
- Curing status interpretation: Only samples younger than 28 days can physically be "Pending 28D Curing". Older samples without tests are reported as "unrecorded / missing".

---

## TESTING & QUALITY GATES

- **Test Suite**: `pytest` runs offline tests with mock keys and synthetic data by default.
- **Synthetic Fixtures**: Located in `tests/fixtures/` (`synthetic_cement_data.csv`, `sparse_cement_data.csv`).
- **Browser Smoke Test**: Run via Chromium:
  ```bash
  PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium node tests/smoke_dashboard.mjs
  ```
- **Secret Scan**: Run before every commit and push:
  ```bash
  betterleaks git .
  ```
