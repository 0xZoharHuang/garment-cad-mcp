# Setup

## macOS arm64 control plane

```bash
./scripts/bootstrap-macos.sh
cmake --build --preset valentina-guis
uv run garmentcad doctor
```

Bootstrap creates the main uv environment, a separately locked GarmentCode compatibility environment,
and the pinned universal macOS CPU Warp library. The build produces Valentina, Tape, and Puzzle and
runs native command replay tests. Run the complete verification with:

```bash
./scripts/test.sh
```

That repeatable full check covers generated contracts, Python, native Valentina/Tape/Puzzle,
native GarmentCode/exports, and doctor. For direct SDK use outside MCP, set:

```bash
export GARMENTCAD_VALENTINA_COMMAND="$PWD/scripts/valentina-command-host.sh"
export GARMENTCAD_GARMENTCODE_COMMAND="$PWD/scripts/garmentcode-command-host.sh"
```

Claude Code loads the wrappers from `.mcp.json`. Codex CLI, the Codex desktop app, and the Codex IDE
extension load `.codex/config.toml` after the repository is trusted. Commands default to
preview-only. Codex uses eager tool registration; Claude Code retains the smaller lazy catalog.

Verify the Codex connection in a new session:

```bash
codex -C "$PWD"
# /mcp should show valentina_cad and garmentcode_cad
```

The core tools are always present: `project_create`, `project_import`, `project_open`,
`project_status`, `catalog_search`, `resource_read`, `command_preview`, `changeset_commit`,
`changeset_discard`, and `revision_revert`. `project_create` is
available from `valentina-mcp` alone, so a CAD client does not need GarmentCode merely to begin a
new pattern. The shell wrappers resolve the repository path themselves and do not require an
absolute path in Codex configuration.

Codex 0.144.1 has a client-side config merge bug when per-server approval/time-out fields are
overridden on a project-scoped STDIO server; the checked-in config intentionally contains only the
portable command and arguments. Configure optional policy globally after upgrading the client.

Launch each upstream GUI through the reproducible wrappers:

```bash
./scripts/launch-guis.sh valentina
./scripts/launch-guis.sh tape
./scripts/launch-guis.sh puzzle
./scripts/launch-guis.sh garmentcode
```

When editing project truth, pass the project directory. The Valentina/Tape/Puzzle launchers open the
canonical document and hold the same single-writer lock used by SDK/MCP commits for the GUI lifetime;
status/resource reads remain available. On exit, a changed document is recorded as an append-only
`project.gui_save` revision using its pre-session snapshot; an unchanged session adds no revision.
GarmentCode uses the path to prefill its optional bridge:

```bash
./scripts/launch-guis.sh valentina ./projects/sample
./scripts/launch-guis.sh tape ./projects/sample
./scripts/launch-guis.sh puzzle ./projects/sample
./scripts/launch-guis.sh garmentcode ./projects/sample
```

The repository-launched GarmentCode GUI includes a collapsible **Garment Project / AutoDL** panel
for project status, submission, polling, and revision-safe artifact download. It calls the same
Python client as MCP and the CLI; the original GarmentCode editor remains unchanged outside that
optional panel.

There is no separate browser CAD editor in this repository. During agent work, inspect compact MCP
preview images; open Valentina/Tape/Puzzle for full native CAD inspection. A GUI opened in editing
mode owns the single-writer lock, so an agent can continue reading but cannot commit concurrently.

## Public real-pattern qualification

```bash
uv run garmentcad-corpus manifest
GARMENTCAD_VALENTINA_COMMAND="$PWD/scripts/valentina-command-host.sh" \
  uv run garmentcad-corpus validate --output build/reports/real-patterns
```

The runner never edits upstream fixtures. It creates isolated temporary projects, obtains two
native semantic snapshots, adds an unused increment through the native command service, commits,
reopens, appends a reverse revision, and requires exact restoration of both semantic snapshot and
`.val` bytes. It writes JSON, HTML, and a resumable partial report. Production timeouts receive one
120-second retry; regression fixtures remain bounded at ten seconds.

The 2026-08-10 Apple Silicon run classified 85 files as 61 pass, 13 missing dependency, seven
bounded regression rejection, two expected rejection, and two invalid XML. All 20 self-contained
production-like cases passed; ten additional production-like cases cannot be qualified because the
public upstream corpus omits their referenced measurement assets.

## Valentina revision to GarmentCode

The SDK and `assembly_sync_from_pattern` MCP tool ask the native Valentina host to expand the
current `pattern/main.val`; they never parse or edit its XML in Python. Optional sewing semantics
live in `assembly/sewing-sidecar.json` and reference deterministic edge aliases from the native
snapshot:

```json
{
  "schema_version": "1.0",
  "interfaces": [
    {"alias": "front.side", "edges": ["FrontPanel.edge.0000"]},
    {"alias": "back.side", "edges": ["BackPanel.edge.0000"], "reverse": true}
  ],
  "stitches": [
    {
      "alias": "side.seam",
      "interface_a": "front.side",
      "interface_b": "back.side",
      "direction": "opposed"
    }
  ]
}
```

```python
from garmentcad.sdk import GarmentSDK

preview = GarmentSDK("./project").sync_assembly_from_pattern()
```

The contracts are generated as `schemas/pattern-snapshot.schema.json` and
`schemas/sewing-sidecar.schema.json`.

Export the current assembly through the same pinned native object model. OBJ and USDA contain the
panel initial 3D placements in millimetres; curved edges are sampled by GarmentCode before
triangulation. Repeating an export returns the same content-addressed URIs.

```python
artifacts = GarmentSDK("./project").export_garmentcode(["json", "obj", "usd"])
```

## AutoDL GPU worker

Clone this repository on AutoDL, then:

```bash
./scripts/bootstrap-autodl.sh
./scripts/start-worker.sh
```

Bootstrap builds the fixed Warp fork against the instance CUDA toolkit, installs fixed GarmentCode,
and runs `scripts/autodl-runner.py --preflight`. The runner consumes the self-contained bundle,
generates the stitched BoxMesh, runs Warp simulation, writes structured metrics, and renders every
view named by the project camera config. After the official smoke job succeeds, save the configured
instance as an AutoDL private image.

With the worker running, execute the real pinned official-asset acceptance from a second shell:

```bash
uv run scripts/smoke-autodl.py --worker-url http://127.0.0.1:8765
```

It requires a successful shirt BoxMesh, CUDA simulation, front/back/left/right PNGs, and a cache hit
on identical resubmission. A fixture runner is never accepted by this command.

Keep the worker bound to loopback and open an SSH tunnel from the Mac:

```bash
export GARMENTCAD_AUTODL_HOST=autodl-host
export GARMENTCAD_AUTODL_USER=root
./scripts/open-autodl-tunnel.sh
export GARMENTCAD_WORKER_URL=http://127.0.0.1:8765
```

The project manifest must select a body mesh (`OBJ`, `PLY`, or `GLB`), corresponding body-measurement
YAML and vertex-segmentation JSON, fabric JSON/YAML, simulation JSON/YAML, and camera JSON. Body mesh
coordinates follow GarmentCode's body-asset convention and are metres; pattern coordinates and
camera locations remain public millimetres. A minimal camera file is:

`GarmentSDK.configure_simulation` and the `simulation_configure` MCP tool accept either existing
project-relative files or absolute source files. Absolute sources are frozen inside the preview and
installed into `simulation/` only on commit, so a reverse revision removes them cleanly.

```json
{
  "schema_version": "1.0",
  "resolution": [800, 800],
  "views": [
    {"name": "front", "side": "front"},
    {"name": "back", "side": "back"},
    {"name": "left", "azimuth_deg": -90},
    {"name": "right", "azimuth_deg": 90}
  ]
}
```
