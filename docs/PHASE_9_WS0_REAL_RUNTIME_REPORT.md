# Phase 9 WS0 — real runtime recovery

**PASS.** The regular Windows account started Uvicorn with the real V3 snapshot on `127.0.0.1:8765`. The app returned JSON readiness `READY`, mode `REAL_RESEARCH`, model `1.0.0`, snapshot `phase853_v3_20261122` and `production_approved=false`.

## Diagnosis and recovery

The listener on port 8765 initially belonged to the previous project-controlled synthetic browser audit (Uvicorn PID 12152). The earlier real launch ran under the ordinary Windows user `HP`. It failed first at `Path.stat()` with WinError 5 on the two required files, before SQLite opened. In Python 3.14, `Path.is_file()` suppresses that filesystem error, which the Composite History probe surfaced as `HISTORY_MISSING`.

The parent research directory could be traversed under the runtime user, whose `SeChangeNotifyPrivilege` was enabled. The V3 directory was owned by the sandbox principal and had a protected DACL granting owner rights, SYSTEM and administrators access. Its two files inherited those entries. They had ordinary Archive attributes. The ordinary runtime account could neither inspect the V3 directory nor read its files. The sandbox owner context could read them. The model, metadata and other inputs required for readiness were readable in the recovered runtime.

The recovery kept the existing trusted path, files and owner. The owner granted the exact runtime SID read/execute on the V3 directory only and read on its SQLite and manifest only. Neither grant is propagated. No copy or replacement of the pinned snapshot was needed.

| File | SHA-256 before and after |
|---|---|
| `laliga_composite.sqlite3` | `110f336daf40a6957cad6f5dc6c56298619ee96a52224b0fc4aa47a6b311b40e` |
| `manifest.json` | `22f32a8bd31a7b27f2183ec4b594b79a36f9421bc0727a01d297123155735e12` |

## Live checks

All eight endpoints returned HTTP 200 with real JSON. The final Phase 9 process on port 8765 (Uvicorn PID 20652) also logged 200 for each. The SQLite integrity check was `ok` and the foreign-key check returned zero rows.

| Endpoint under `/api/v1` | Verified response |
|---|---|
| `health/ready` | Ready, trusted real snapshot and frozen model |
| `bootstrap` | Latest catalogue season 2026, real namespace, operator writes disabled |
| `teams` | 31 teams across catalogue seasons 2019–2026 |
| `fixtures` | 380 season-2026 entries |
| `data-status` | Pinned DB hash, real registry counts and freshness |
| `historical/team-stats` | Valencia, 2026, 12 observed Sportmonks matches |
| `historical/match-analysis` | Valencia vs Real Madrid, 2025 Last 5, five Understat observations |
| `model/summary` | Frozen Linear Regression 1.0.0 and 13 ordered inputs |

Request details, process logs and runtime evidence are local under `data/external/multisource/phase9/`. The final gate records a PowerShell startup procedure and baseline integrity results.
