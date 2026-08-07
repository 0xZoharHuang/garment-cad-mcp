# Valentina native command host

The MCP adapter intentionally fails closed when `GARMENTCAD_VALENTINA_COMMAND` is absent. A native
host must be built inside the pinned Valentina source tree and link the existing model/tool libraries.

For every public construction action, decode arguments into the corresponding tool's `InitData`, run
the same validation used by the GUI, call its static `Create` method against a cloned document during
preview, and save that cloned `.val` beneath the supplied change-set directory. Commit atomically
installs the candidate. Tape and Puzzle actions follow the same rule. No handler may synthesize XML.

The stable action list is `garmentcad.catalog.VALENTINA_TOOLS`; additions require an explicit catalog
review when updating the pinned Valentina commit.
