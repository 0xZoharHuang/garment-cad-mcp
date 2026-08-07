# Architecture

The system keeps CAD truth separate from agent conversation state.

```text
natural language + reference images + body measurements + constraints
                              |
                       GPT-5.6 / VLM agent
                    /         |          \
             atomic MCP   Python recipe   visual comparison
                  |             |                 ^
                  +------ typed SDK --------------+
                              |
                 preview -> validate -> commit
                    |                       |
            candidate change-set       new revision
                    |                       |
          .val (canonical 2D) + assembly.json (canonical sewing)
                              |
                    GarmentCode conversion
                        mm --------> cm
                              |
                  AutoDL Warp simulation worker
                              |
                    mesh + metrics + screenshots
```

## Why tools and code coexist

Atomic tools are the best control surface for common geometric edits: schemas generated from the
native handler contracts constrain the
VLM, every action can be previewed, and failures have small blast radii. Python recipes are better
for repetitive parametric construction, loops, and formulas. Recipes call the same typed SDK; they
do not edit `.val` or `assembly.json` directly. This gives the agent expressive code without making
file formats its unofficial API.

## Project contract

```text
project/
|-- garment.json                 identity, units, current revision
|-- pattern/main.val             canonical Valentina pattern
|-- measurements/                Tape files
|-- layout/                      Puzzle outputs
|-- assembly/assembly.json       panel placement and stitch graph, in mm
|-- simulation/{bodies,fabrics}/ explicit physical inputs
|-- artifacts/                   exports and downloaded renders
`-- .garmentcad/
    |-- changesets/              preview tokens and candidate files
    |-- revisions/               append-only revision metadata
    |-- snapshots/               preimages used by reverse revisions
    `-- project.lock             single-writer lock
```

A preview records its base revision. Commit rejects it if another writer has moved the project.
UUIDs provide durable identity; aliases remain readable handles for agents and humans.
New projects copy a minimal Valentina-authored seed pattern; subsequent `.val` changes only pass
through the native command service.

The checked-in `atomic-tools.schema.json` and generated `AtomicCommands` class are rebuilt from the
pinned native handlers. CI fails if handler coverage, schemas, generated recipe types, or the lazy
MCP input schemas drift apart.

## Boundary with GarmentCode

GarmentCode is still the parametric garment library and Warp simulation integration. This repository
adds the missing product/system layer: Valentina-authored 2D truth, transactional multi-file project
state, small agent-safe commands, revision concurrency, remote jobs, and uniform results. It does not
replace GarmentCode's design grammar; it wraps and interoperates with its serialized pattern API.

## Valentina command boundary

Pattern commands use a newline-JSON process contract selected by `GARMENTCAD_VALENTINA_COMMAND`:

```text
commands.preview { project_root, change_set_id, operations[] } -> { summary, resources[] }
commands.commit  { project_root, change_set_id } -> { ok }
```

The command host must invoke Valentina's own construction `InitData/Create` paths so the GUI and
agent produce the same objects. The MCP never writes Valentina XML itself. The Python adapter and all
49 construction endpoints are present; the patched C++ host is the remaining native integration
target documented in `docs/VALENTINA_HOST.md`.
