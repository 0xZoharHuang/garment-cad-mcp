# garment-cad-mcp

Agent-facing garment CAD control plane built around pinned Valentina and GarmentCode sources.

It provides two local stdio MCP servers, a shared Python SDK, preview/commit transactions, append-only
revisions, GarmentCode-compatible serialization, and a serial AutoDL GPU worker API. External geometry
uses millimetres; the GarmentCode facade converts to centimetres at its boundary.

```python
from garmentcad import GarmentSDK

cad = GarmentSDK("./projects/sample")
preview = cad.panel_create(
    "front",
    [[0, 0], [420, 0], [360, 620], [0, 620]],
)
# Inspect preview.summary, then commit explicitly:
# garmentcad commit <preview.preview_token> --path ./projects/sample
```

Valentina, Tape, and Puzzle recipes use the schema-generated typed atomic surface. The same
contracts are embedded in lazily loaded MCP tool schemas:

```python
preview = cad.commands.pattern_along_line(
    alias="front.armhole.guide",
    first_point={"alias": "front.shoulder"},
    second_point={"alias": "front.underarm"},
    length_mm=35,
)
```

Quick start:

```bash
./scripts/bootstrap-macos.sh
uv run garmentcad create ./projects/sample
./scripts/test.sh
```

Read [the architecture](docs/ARCHITECTURE.md), [setup guide](docs/SETUP.md), and
[native Valentina host contract](docs/VALENTINA_HOST.md). The
[acceptance ledger](docs/ACCEPTANCE.md) separates locally proven gates from the pending real-GPU
evidence. See `THIRD_PARTY.md` for exact upstream commits and licenses.

## Current integration status

- GarmentCode panel/interface/stitch transactions, SDK, and MCP: implemented and tested.
- Remote worker upload, serial execution, cache, polling, artifacts, and screenshot enforcement:
  implemented together with the pinned Warp/GarmentCode runner, AutoDL bootstrap, and SSH tunnel;
  deployment supplies the body assets and an NVIDIA AutoDL instance.
- Valentina/Tape/Puzzle native command services, MCP catalog, and schema-generated typed recipes:
  implemented with complete reviewed handler coverage.
- Native previews include compact image resources; full coordinates, change-sets, assembly data,
  exports, and simulation logs remain URI-addressable on demand.

The boundary remains explicit: this project never edits `.val` XML behind Valentina's back.
