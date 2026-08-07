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

Quick start:

```bash
./scripts/bootstrap-macos.sh
uv run garmentcad create ./projects/sample
uv run pytest
```

Read [the architecture](docs/ARCHITECTURE.md), [setup guide](docs/SETUP.md), and
[native Valentina host contract](docs/VALENTINA_HOST.md). See `THIRD_PARTY.md` for exact upstream
commits and licenses.

## Current integration status

- GarmentCode panel/interface/stitch transactions, SDK, and MCP: implemented and tested.
- Remote worker upload, serial execution, cache, polling, artifacts, and screenshot enforcement:
  implemented; deployment supplies the pinned Warp runner and GPU assets.
- Valentina/Tape/Puzzle MCP catalog and process adapter: implemented.
- Native Valentina C++ command host: specified but not yet implemented. Pattern calls fail closed until
  `GARMENTCAD_VALENTINA_COMMAND` points to a host using Valentina's own `InitData/Create` APIs.

That last boundary is intentionally explicit: this project never edits `.val` XML behind Valentina's
back, and it does not claim native parity before those C++ handlers exist.
