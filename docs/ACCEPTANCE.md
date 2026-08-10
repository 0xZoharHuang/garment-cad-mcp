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
| 10. Public real-pattern CAD fidelity | 85-file corpus runner; 20/20 self-contained production-like patterns snapshot, mutate, commit, reopen and reverse byte-exactly; ten production-like patterns have missing upstream measurements | Passing for self-contained public corpus |
| 11. From-zero client drafting | Bodice, shirt and trouser qualification drafts create 3/6/4 formula-driven pieces with seam allowance, passmarks, internal paths, measurement redraft and PDF/AAMA/ASTM export | Passing |
| 12. Codex MCP dogfood | Codex 0.144.1 project-scoped STDIO config eagerly exposed `pattern_end_line`; Codex created a project, produced and read a native preview, and left revision 0 uncommitted | Passing |

## Remaining proof gates

1. Run `uv run scripts/smoke-autodl.py` against the supplied AutoDL GPU instance. Local fixture
   results cannot satisfy this gate.
2. Supply the ten missing public measurement assets before those corpus patterns can be counted as
   CAD compatibility passes.

The qualification drafts are deterministic integration fixtures, not professionally approved
blocks. Production readiness still requires patternmaker review, grading, fabric/shrinkage rules,
sewability checks, and physical or validated 3D fit evidence.

The GarmentCode coverage report still audits the pinned public transformation surface, but the MCP
deliberately exposes only sewing, component, and 3D-placement semantics owned by GarmentCode.
Panel/edge/dart construction actions were removed from this MCP because Valentina is the sole 2D
CAD truth. `Component.rotate_to` remains recorded separately because upstream itself raises
`NotImplementedError`.
