# LogViewer Source Sidebar — Fix Plan

**Component:** `LogViewer` in `services/dashboard/src/pages/RunDetail.tsx`  
**Issue:** With many test log sources (`test:02edd147`, …), the left sidebar (`w-44`, `truncate`) clips labels and stacks sources awkwardly inside a fixed `600px` column.

---

## Problem diagnosis

Current structure (~lines 210–248 in `RunDetail.tsx`):

```tsx
<div className="flex gap-3 h-[600px]">
  <aside className="w-44 shrink-0 flex flex-col gap-1 overflow-y-auto">
    {/* Sources + Level filters in one scroll column */}
    {sortedSources.map(src => (
      <button className="... truncate" title={src}>{src}</button>
    ))}
  </aside>
  <div className="flex-1 ...">{/* log pane */}</div>
</div>
```

| Issue | Effect |
|--------|--------|
| Fixed width `w-44` (176px) | `test:02edd147`-style IDs truncate mid-string |
| `truncate` on every button | Ellipsis without readable labels; `title` only on hover |
| Flat sorted list | Infrastructure (`advancer`, `evm-reader`) mixed with dozens of `test:*` sources |
| Single scroll column | Sources + level filters compete inside 600px height |
| No search in sidebar | Hard to find one test among 50+ sources |

The layout works for ~10 sources; it breaks when a full run logs per-test containers.

---

## Design goals

1. **Readable labels** — full or sensibly shortened names, not clipped mid-word.
2. **Scalable list** — 50+ sources without cramped buttons.
3. **Fast filtering** — find “that failing test” in seconds.
4. **Preserve behavior** — multi-select sources, colors, level filter, log pane unchanged.
5. **Minimal scope** — UI-only in dashboard unless grouping needs API help.

---

## Options (ranked)

### Option A — Grouped collapsible sidebar (recommended)

**Layout**

```
┌─────────────────────────┬──────────────────────────────┐
│ Sources          [search]│  Search logs…  ⬇ Live  📥    │
│ ○ All sources            │                              │
│ ▼ Services (6)           │  log lines…                  │
│   advancer  claimer …    │                              │
│ ▼ Infrastructure (4)     │                              │
│   anvil  deploy  build   │                              │
│ ▼ Tests (42)             │                              │
│   02edd147  03be9262 …   │                              │
├─────────────────────────┤                              │
│ Level                    │                              │
│ All / ≥ warn / Error     │                              │
└─────────────────────────┴──────────────────────────────┘
```

**Behavior**

- Parse sources: `test:<id>` → **Tests**; known service names → **Services**; rest → **Other**.
- Collapsible sections (default: Services expanded, Tests collapsed with count).
- Section-level “select all / clear”.
- Sidebar width `w-56`–`w-64` or `min-w-[12rem] max-w-[20rem]`.
- Source search filters buttons in sidebar (separate from log message search).

**Pros:** Clear hierarchy, works at scale, small diff.  
**Cons:** Needs grouping rules + a bit of state.

---

### Option B — Resizable split pane

Keep flat list but:

- `resize` handle between sidebar and log pane (`min-w-[140px] max-w-[40%]`).
- Remove `truncate`; use `break-all` or two-line clamp (`line-clamp-2`).
- Optional: remember width in `localStorage`.

**Pros:** User controls width; simple.  
**Cons:** Doesn’t fix long lists or mixing services vs tests.

---

### Option C — Combobox / multi-select dropdown

Replace sidebar with a **“Sources (3 selected)”** popover:

- Command palette style: search, checkboxes, groups.
- Log pane gets full width.

**Pros:** Best for very large N; mobile-friendly.  
**Cons:** Filters hidden until opened; bigger UX change.

---

### Option D — Tabs instead of sidebar

Tabs: `All | Services | Tests | Selected` — tests tab shows searchable grid/list.

**Pros:** Familiar pattern.  
**Cons:** Extra click to switch; less “at a glance” than grouped sidebar.

---

## Recommended approach: A + B (light)

Phase 1 fixes the pain; Phase 2 polishes.

### Phase 1 — Quick wins (1–2 hours)

1. **Widen sidebar** — `w-44` → `w-60` or `min-w-[15rem]`.
2. **Fix text clipping**
   - Remove `truncate` on source buttons.
   - Use `text-left break-all` or monospace for `test:*` IDs.
   - Show short label in UI: `test:02edd147` → `02edd147` (strip prefix), full string in `title`.
3. **Split sidebar sections vertically**
   - Top: sources (`flex-1 min-h-0 overflow-y-auto`).
   - Bottom: level filter (`shrink-0 border-t`) so levels aren’t scrolled away.
4. **Source sidebar search** — small input above list; filter `sortedSources` client-side.

### Phase 2 — Grouping & scale (2–4 hours)

5. **Group sources** — utility `groupLogSources(sources: string[])`:
   - `Services`: advancer, claimer, evm-reader, validator, jsonrpc-api, database
   - `Tests`: `test:*`
   - `Other`: anvil, deploy, build, etc.
6. **Collapsible groups** — `<details>` or small `useState` per group; persist open/closed in `sessionStorage`.
7. **Group actions** — “All tests”, “Clear tests”, keep global “All sources”.
8. **Counts** — `Tests (42)` next to group header.

### Phase 3 — Optional polish

9. **Resizable sidebar** — drag handle (e.g. `react-resizable-panels` or ~20 lines pointer handlers).
10. **Virtualized list** — only if groups still lag with 200+ sources (`@tanstack/react-virtual` on test group).
11. **Extract component** — `LogViewer.tsx` + `LogSourcePanel.tsx` for tests and reuse.

---

## Implementation sketch

```ts
// utils/logSources.ts
type SourceGroup = 'services' | 'tests' | 'other'

const SERVICE_NAMES = new Set([
  'advancer', 'claimer', 'evm-reader', 'validator', 'jsonrpc-api', 'database',
])

function parseSource(src: string): { group: SourceGroup; label: string } {
  if (src.startsWith('test:')) return { group: 'tests', label: src.slice(5) }
  if (SERVICE_NAMES.has(src)) return { group: 'services', label: src }
  return { group: 'other', label: src }
}

function groupSources(sources: Set<string>) {
  const groups: Record<SourceGroup, string[]> = {
    services: [],
    tests: [],
    other: [],
  }
  for (const s of sources) groups[parseSource(s).group].push(s)
  for (const k of Object.keys(groups) as SourceGroup[]) groups[k].sort()
  return groups
}
```

**Layout change (Tailwind)**

```tsx
<div className="flex gap-3 h-[min(70vh,800px)]">
  <aside className="w-60 shrink-0 flex flex-col min-h-0 border-r border-rvp-border">
    <SourceSearch value={srcSearch} onChange={setSrcSearch} />
    <div className="flex-1 min-h-0 overflow-y-auto">
      <SourceGroup name="Services" sources={...} />
      <SourceGroup
        name="Tests"
        sources={...}
        defaultCollapsed={tests.length > 8}
      />
    </div>
    <LevelFilter ... />
  </aside>
  <div className="flex-1 flex flex-col min-w-0 ...">...</div>
</div>
```

No backend changes required unless you later want the API to return pre-grouped sources from `logSources`.

---

## Acceptance criteria

- [ ] 50+ sources: no horizontal clip; test IDs readable (full or `02edd147` + tooltip).
- [ ] Level filters always visible without scrolling past all sources.
- [ ] Sidebar search finds a test ID in &lt;2 keystrokes.
- [ ] Services vs tests visually separated; tests collapsible when &gt;8.
- [ ] Existing: multi-select filter, colors, log search, auto-scroll, download unchanged.
- [ ] Works at 1280px and 1920px width; sidebar doesn’t steal &gt;35% of log area.

---

## What not to do

- **Only increase height** (`h-[800px]`) — doesn’t fix truncation or list chaos.
- **Smaller font only** — hurts accessibility.
- **Dropdown-only** without grouping — still painful with 50 checkboxes.

---

## Suggested order of work

| Step | Task | Effort |
|------|------|--------|
| 1 | Split sources / level layout + widen + label formatting | S |
| 2 | Sidebar source search | S |
| 3 | Group + collapse Tests/Services | M |
| 4 | Resizable sidebar (optional) | M |
| 5 | Extract `LogSourcePanel` + unit test grouping util | S |

---

## Related files

| File | Role |
|------|------|
| `services/dashboard/src/pages/RunDetail.tsx` | `LogViewer` implementation |
| `HANDOVER_log_capture.md` | Log capture architecture |
| `README.md` | LogViewer feature checklist |
