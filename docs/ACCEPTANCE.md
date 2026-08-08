# Acceptance ledger

This ledger distinguishes implemented behavior from the external GPU gate.
`./scripts/test.sh` is the authoritative repeatable Apple Silicon check.

| Final acceptance | Evidence | State |
| --- | --- | --- |
| 1. Open and atomically modify an existing `.val` | Native collection fixtures, compact preview PNG, commit/reopen, all catalog actions replayed; every GUI constructor crosses the typed command envelope and representative dialog/headless XML is byte-equivalent | Passing |
| 2. Typed Python recipe, preview, commit | Generated `AtomicCommands` and `AssemblyCommands`, schema/MCP-signature drift checks, canonical SDK/MCP change-set equivalence, and documented `Project` namespace contract | Passing |
| 3. Continue in GUI and refresh Agent state | Project-aware GUI launcher holds writer lock; changed sessions append reversible `project.gui_save` revisions | Passing for repository launcher |
| 4. Tape change triggers parametric recalculation | Native `.vit`/`.vst` lifecycle, personal/file metadata, dimension labels and restrictions, corrections/value aliases, embedded measurement images, individual/multisize CSV import/export, plus a 100 mm to 200 mm measurement-driven piece snapshot test | Passing |
| 5. Puzzle nesting and all implemented exports | Official MaleShirt layout, reopen, sheet/piece editing, z-order, grainline rotation, trash/reset, crop and native validity checks, plus runtime validation of all 24 implemented `LayoutExportFormats` values; upstream `NC` remains explicitly reserved | Passing |
| 6. Convert current revision to GarmentCode | Native Valentina snapshot, sewing sidecar, millimetre/centimetre boundary and round-trip tests | Passing |
| 7. AutoDL stitch/simulate/multiview | Worker/fixture contract passes; `scripts/smoke-autodl.py` requires the pinned runner, CUDA result diagnostics, four PNGs and cache reuse | Awaiting an AutoDL instance |
| 8. Structured failure and safe rollback | Invalid preview, immutable candidate, stale GUI save, injected commit failure, Worker failure/timeout/cancel/restart tests | Passing |
| 9. Doctor and full tests on Apple Silicon | `scripts/test.sh`; doctor verifies exact pins, native hosts and universal CPU Warp | Passing |

## Remaining proof gates

1. Run `uv run scripts/smoke-autodl.py` against the supplied AutoDL GPU instance. Local fixture
   results cannot satisfy this gate.

The GarmentCode facade coverage check audits every public transformation on the pinned `Panel`,
`Edge`, `EdgeSequence`, `Interface`, and `Component` classes. Shared parameterized actions implement
the mappings; `Component.rotate_to` is recorded separately because upstream itself always raises
`NotImplementedError`.
