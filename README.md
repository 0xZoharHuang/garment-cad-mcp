# garment-cad-mcp

Agent-facing garment CAD control plane built around pinned Valentina and GarmentCode sources.

It provides two local stdio MCP servers, a shared Python SDK, preview/commit transactions,
append-only revisions, a native GarmentCode document, and a serial AutoDL GPU worker API. Public
geometry uses millimetres; the native GarmentCode host converts to centimetres at its boundary.

```python
from garmentcad import GarmentSDK

cad = GarmentSDK("./projects/sample")
preview = cad.commands.pattern_along_line(
    alias="front.armhole.guide",
    first_point={"alias": "front.shoulder"},
    second_point={"alias": "front.underarm"},
    length_mm=35,
)
# Inspect preview.summary, then commit explicitly:
# garmentcad commit <preview.preview_token> --path ./projects/sample
```

Valentina, Tape, and Puzzle recipes use the schema-generated typed atomic surface. They create all
2D geometry; GarmentCode only receives a read-only projection for sewing and 3D placement. The same
contracts are embedded in lazily loaded MCP tool schemas:

```python
assembly_preview = cad.sync_assembly_from_pattern(bindings={"interfaces": [], "stitches": []})
```

Quick start:

```bash
./scripts/bootstrap-macos.sh
uv run garmentcad create ./projects/sample
./scripts/test.sh
```

Both MCP servers can create a project from the minimal Valentina-authored seed. Claude Code uses
`.mcp.json`; local Codex clients use `.codex/config.toml`. Codex starts the atomic catalogs eagerly
because Codex 0.144.1 does not refresh tools registered after `catalog_search`. The stable
`command_preview` core tool remains available to clients that cannot refresh a dynamic catalog.

Create complete multi-piece qualification drafts without editing `.val` XML:

```bash
uv run python scripts/recipes/draft_qualification_pattern.py bodice /tmp/bodice --create
uv run python scripts/recipes/draft_qualification_pattern.py shirt /tmp/shirt --create
uv run python scripts/recipes/draft_qualification_pattern.py trousers /tmp/trousers --create
```

Run the public real-pattern qualification suite and open its HTML report:

```bash
GARMENTCAD_VALENTINA_COMMAND="$PWD/scripts/valentina-command-host.sh" \
  uv run garmentcad-corpus validate --output build/reports/real-patterns
open build/reports/real-patterns/report.html
```

Read [the architecture](docs/ARCHITECTURE.md), [setup guide](docs/SETUP.md), and
[native Valentina host contract](docs/VALENTINA_HOST.md). The
[acceptance ledger](docs/ACCEPTANCE.md) separates locally proven gates from the pending real-GPU
evidence. See `THIRD_PARTY.md` for exact upstream commits and licenses.

## Current integration status

- GarmentCode native-document sync, placement, interface/stitch transactions, SDK, and MCP:
  implemented and tested. There is no Python-side panel geometry kernel.
- Remote worker upload, serial execution, cache, polling, artifacts, and screenshot enforcement:
  implemented together with the pinned Warp/GarmentCode runner, AutoDL bootstrap, and SSH tunnel;
  deployment supplies the body assets and an NVIDIA AutoDL instance.
- Valentina/Tape/Puzzle native command services, MCP catalog, and schema-generated typed recipes:
  implemented with complete reviewed handler coverage.
- Native previews include compact image resources; full coordinates, change-sets, assembly data,
  exports, and simulation logs remain URI-addressable on demand.
- The checked-in public corpus contains 85 `.val` files: the current strict run passed every
  self-contained production-like case; missing measurement assets and regression rejections remain
  visible as separate report categories.

The boundary remains explicit: this project never edits `.val` XML behind Valentina's back.
Passing this suite establishes CAD transport and transaction fidelity, not that an unaudited agent
draft is fit for manufacture.
