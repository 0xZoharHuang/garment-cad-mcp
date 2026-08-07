# Acceptance ledger

This ledger distinguishes implemented behavior from the two gates that require stronger evidence.
`./scripts/test.sh` is the authoritative repeatable Apple Silicon check.

| Final acceptance | Evidence | State |
| --- | --- | --- |
| 1. Open and atomically modify an existing `.val` | Native collection fixtures, compact preview PNG, commit/reopen, all catalog actions replayed | Passing |
| 2. Typed Python recipe, preview, commit | Generated `AtomicCommands`, schema drift check, documented `Project` namespace contract | Passing |
| 3. Continue in GUI and refresh Agent state | Project-aware GUI launcher holds writer lock; changed sessions append reversible `project.gui_save` revisions | Passing for repository launcher |
| 4. Tape change triggers parametric recalculation | Native `.vit` lifecycle plus a 100 mm to 200 mm measurement-driven piece snapshot test | Passing |
| 5. Puzzle nesting and DXF/PDF export | Official MaleShirt layout, reopen, AAMA/ASTM DXF, PDF, SVG and HPGL checks | Passing |
| 6. Convert current revision to GarmentCode | Native Valentina snapshot, sewing sidecar, millimetre/centimetre boundary and round-trip tests | Passing |
| 7. AutoDL stitch/simulate/multiview | Worker/fixture contract passes; `scripts/smoke-autodl.py` requires the pinned runner, CUDA result diagnostics, four PNGs and cache reuse | Awaiting an AutoDL instance |
| 8. Structured failure and safe rollback | Invalid preview, immutable candidate, stale GUI save, injected commit failure, Worker failure/timeout/cancel/restart tests | Passing |
| 9. Doctor and full tests on Apple Silicon | `scripts/test.sh`; doctor verifies exact pins, native hosts and universal CPU Warp | Passing |

## Remaining proof gates

1. Run `uv run scripts/smoke-autodl.py` against the supplied AutoDL GPU instance. Local fixture
   results cannot satisfy this gate.
2. The native command service and GUI both call Valentina `InitData/Create`, but the stronger planned
   assertion that every GUI dialog first emits the same Command DTO has not yet been demonstrated for
   every constructible Tool. Handler coverage and headless replay are complete; dialog-to-DTO
   equivalence remains a separate native refactor/test gate.
