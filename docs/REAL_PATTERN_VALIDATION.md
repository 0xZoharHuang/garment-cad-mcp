# Real-pattern qualification

This suite answers a narrow question: can the MCP/native command boundary preserve real Valentina
CAD state while previewing, committing, reopening, and reversing an operation? It does not score an
agent's fashion interpretation or certify a pattern for manufacturing.

## Gates

For every parseable, self-contained pattern the runner requires two deterministic native snapshots,
a preview-only parameter mutation, a committed revision, a successful reopen, and a reverse
revision that restores the original semantic snapshot and exact `.val` bytes. Each fixture runs in
an isolated temporary Garment Project; upstream files remain read-only.

Missing or unsafe measurement references, intentionally invalid XML, expected invalid documents,
and bounded failures from historical regression fixtures are reported separately. They never count
as successful CAD opens and never dilute the production-like pass rate.

## Commands and artifacts

```bash
uv run garmentcad-corpus manifest
GARMENTCAD_VALENTINA_COMMAND="$PWD/scripts/valentina-command-host.sh" \
  uv run garmentcad-corpus validate --output build/reports/real-patterns
```

The output directory contains `manifest.json`, `report.json`, and `report.html`. During an interrupted
run, `report.partial.json` is atomically updated and used for resumption. Use `--representative` for
the twelve-case development subset and `--keep-workspaces` only when debugging a failure.

## Current evidence

The 2026-08-10 run on Apple Silicon inspected 85 public `.val` files:

- 61 passed the full applicable transaction chain.
- 13 were dependency-missing, including ten production-like patterns whose referenced public
  measurement files are unavailable or unsafe to relocate without modifying their XML.
- Seven historical regression fixtures produced bounded native rejection or timeout diagnostics.
- Two fixtures were expected native rejections and two were invalid XML.
- All 20 self-contained production-like patterns passed; no production-like MCP failure remained.

The corpus includes shirts, trousers, jackets, bodice blocks, lingerie, skirts, embedded images,
legacy schema versions, and high-complexity patterns with dozens of pieces. This is credible CAD
transport evidence, but production pattern quality remains a separate human/domain validation gate.
