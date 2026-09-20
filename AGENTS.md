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

# KUMO KNOWLEDGE BASE

**Generated:** 2026-03-18 | **Commit:** 38518e34 | **Branch:** rozenmd/fix-preview

## OVERVIEW

Cloudflare's React component library (`@cloudflare/kumo`). pnpm monorepo: component library (Base UI + Tailwind v4), Astro docs site, Figma plugin, screenshot worker. ESM-only, Node 24+.

## STRUCTURE

```
kumo/
├── packages/
│   ├── kumo/                     # Component library → see packages/kumo/AGENTS.md
│   ├── kumo-docs-astro/          # Astro docs site → see packages/kumo-docs-astro/AGENTS.md
│   ├── kumo-figma/               # Figma plugin → see packages/kumo-figma/AGENTS.md
│   └── kumo-screenshot-worker/   # Visual regression Worker → see packages/kumo-screenshot-worker/AGENTS.md
├── ci/                           # CI/CD scripts → see ci/AGENTS.md
├── lint/                         # Custom oxlint rules (5 rules in package, 4 at root)
├── .changeset/                   # Changeset files
├── .github/workflows/            # 6 workflow YAMLs (release, pullrequest, preview, etc.)
└── .vite-hooks/                  # Git hooks (Vite+): pre-commit codegen+staged, pre-push changeset validation
```

## WHERE TO LOOK

| Task                 | Location                                         | Notes                                                    |
| -------------------- | ------------------------------------------------ | -------------------------------------------------------- |
| Component API        | `packages/kumo/ai/component-registry.{json,md}`  | Source of truth. Query with `jq` or CLI                  |
| Component source     | `packages/kumo/src/components/{name}/{name}.tsx` | Standard pattern                                         |
| Blocks (installable) | `packages/kumo/src/blocks/`                      | NOT library exports; installed via CLI                   |
| Semantic tokens      | `packages/kumo/src/styles/theme-kumo.css`        | AUTO-GENERATED; edit `scripts/theme-generator/config.ts` |
| Custom lint rules    | `lint/` (4 rules) + `packages/kumo/lint/` (+1)   | Package copy adds `no-deprecated-props`                  |
| Demo examples        | `packages/kumo-docs-astro/src/components/demos/` | Feed into registry codegen                               |
| CI scripts           | `ci/`                                            | Reporter system, versioning, deployment                  |
| Figma generators     | `packages/kumo-figma/src/generators/`            | 37 component generators                                  |

## CONVENTIONS

### Styling (CRITICAL)

- **ONLY semantic tokens**: `bg-kumo-base`, `text-kumo-default`, `border-kumo-line`, `ring-kumo-hairline`
- **NEVER raw Tailwind colors**: `bg-blue-500`, `text-gray-900` → fails lint
- **NEVER `dark:` variant**: dark mode automatic via `light-dark()` in CSS custom properties
- **Exceptions**: `bg-white`, `bg-black`, `text-white`, `text-black`, `transparent`
- **`cn()` utility**: Always compose classNames via `cn("base", conditional && "extra", className)`
- **Surface hierarchy**: `bg-kumo-base` → `bg-kumo-elevated` → `bg-kumo-recessed`
- **Mode/theme**: `data-mode="light"|"dark"` + `data-theme="fedramp"` on parent element

### Components

- **Scaffold new**: `pnpm --filter @cloudflare/kumo new:component` (never create manually)
- **Registry first**: Always check `component-registry.json` before using/modifying a component
- See `packages/kumo/AGENTS.md` for component conventions (variants, forwardRef, displayName)

### Imports

- **No cross-package relative imports**: Use `@cloudflare/kumo` not `../../kumo/src/...` (lint-enforced)
- **ESM-only**: `"type": "module"` throughout. No CJS.

### Changesets

- **Enforced for `packages/kumo/`**: Pre-push hook requires changeset for npm-published library
- **Optional for `kumo-docs-astro`**: Version appears in `/api/version` endpoint (debugging) but nothing depends on it
- **Not needed for `kumo-figma`**: Figma plugin, not published to npm
- **Pre-push hook**: `.vite-hooks/pre-push` validates before push. Bypass: `git push --no-verify` (or `VITE_GIT_HOOKS=0`)
- **AI agents NEVER**: `pnpm version`, `pnpm release`, `pnpm publish:beta`, `pnpm release:production`

### Pull Request Descriptions

PR descriptions are validated by CI. Include this checklist at the end of your PR body:

```markdown
- Reviews
- [ ] bonk has reviewed the change
- [x] automated review not possible because: <your reason here>
- Tests
- [ ] Tests included/updated
- [ ] Automated tests not possible - manual testing has been completed as follows: <description>
- [x] Additional testing not necessary because: <your reason here>
```

Rules:

- Check ONE option in each section (Reviews and Tests)
- If providing a justification (`because:` or `as follows:`), text must follow on the same line
- Indentation is flexible — nested under headers is fine
- Skip validation entirely with the `skip-pr-description-validation` label

## ANTI-PATTERNS

| Pattern                        | Why                                                          | Instead                                     |
| ------------------------------ | ------------------------------------------------------------ | ------------------------------------------- |
| `bg-blue-500`, `text-gray-*`   | Breaks theming, fails lint                                   | `bg-kumo-brand`, `text-kumo-default`        |
| `dark:bg-black`                | Redundant; tokens auto-adapt                                 | Remove `dark:` prefix                       |
| Missing `displayName`          | Breaks React DevTools                                        | Set `.displayName` on forwardRef components |
| Manual component file creation | Misses vite/package.json/index updates                       | Use scaffolding tool                        |
| Editing auto-generated files   | `theme-kumo.css`, `ai/schemas.ts`, `ai/component-registry.*` | Edit source configs, run codegen            |

## COMMANDS

```bash
# Cross-cutting
pnpm dev                                          # Docs dev server (localhost:4321)
pnpm lint                                         # oxlint + custom rules
pnpm typecheck                                    # TypeScript check all packages
pnpm changeset                                    # Create changeset (required for kumo changes)

# Package-specific (see child AGENTS.md for full lists)
pnpm --filter @cloudflare/kumo build              # Build library
pnpm --filter @cloudflare/kumo test               # Vitest
pnpm --filter @cloudflare/kumo codegen:registry   # Regenerate component-registry
pnpm --filter @cloudflare/kumo-figma build        # Build Figma plugin
```

## BUILD PIPELINE

```
kumo-docs-astro demos → dist/demo-metadata.json
                              ↓
kumo codegen:registry → ai/component-registry.{json,md} + ai/schemas.ts
                              ↓
kumo-figma build:data → generated/*.json → vp pack (tsdown) → code.js (IIFE, ES2017)
```

Cross-package dependency: registry codegen requires docs demo metadata. Run `codegen:demos` in docs before `codegen:registry` in kumo.

## TOOLCHAIN

| Tool       | Version   | Notes                                                     |
| ---------- | --------- | --------------------------------------------------------- |
| Node       | ^24.12.0  | Engine constraint (`.node-version`)                       |
| pnpm       | >=10.21.0 | Workspace manager                                         |
| Vite+      | 0.2.2     | Unified toolchain (`vp` CLI): build, test, lint, fmt      |
| TypeScript | 5.9.2     | Via pnpm catalog                                          |
| Vite       | 8.x       | Bundled via vite-plus; library mode (kumo), docs server   |
| Tailwind   | 4.1.17    | v4 with `light-dark()` tokens                             |
| Oxlint     | bundled   | Via `vp lint`; config in vite.config.ts + custom JS rules |
| Oxfmt      | bundled   | Via `vp fmt`; replaced Prettier                           |
| Vitest     | bundled   | Via `vp test`; happy-dom env, v8 coverage                 |
| Changesets | latest    | Version management                                        |
| Astro      | 7.x       | Docs framework                                            |

Lint/format/test config lives in `vite.config.ts` (root and per-package) — there
are no `.oxlintrc.json` / `.prettierrc` files. `vp check` runs format + lint.
The [global Vite+ CLI](https://viteplus.dev/) is optional but recommended for contributors: the binary ships with the local `vite-plus` dependency (`pnpm vp …`), and hooks resolve it from `node_modules/.bin`.

## SECURITY

- **NEVER commit** Figma tokens, npm tokens, or API keys
- `.env` files are gitignored
- `wrangler.jsonc` contains Cloudflare account IDs (not secret but don't expose)

## NOTES

- `ai/component-registry.json`, `ai/component-registry.md` are auto-generated at build time and gitignored (shipped in npm package). `ai/schemas.ts` is a stub for fresh clones (full version generated during build)
- `src/primitives/` (40 files) are auto-generated Base UI re-exports
- Blocks in `src/blocks/` are NOT exported from package index; installed via CLI `kumo add`
- `src/catalog/` is a runtime JSON-UI rendering module (separate concern from component library)
- Single linter: Oxlint via `vp lint` (custom kumo JS rules + native jsx-a11y rules; type-aware + type-checked)
- `PLOP_INJECT_EXPORT` and `PLOP_INJECT_COMPONENT_ENTRY` markers in source for scaffolding
- 6 GitHub Actions workflows exist in `.github/workflows/` (release, pullrequest, preview, preview-deploy, bonk, reviewer)
