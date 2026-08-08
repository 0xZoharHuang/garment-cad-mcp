# Valentina native command host

The MCP adapter intentionally fails closed when `GARMENTCAD_VALENTINA_COMMAND` is absent. The value
is parsed as a command line (so a wrapper plus arguments is supported), and the child receives
`GARMENTCAD_COMMAND_MODE=1` and `QT_QPA_PLATFORM=offscreen`. A native host must be built inside the
pinned Valentina source tree and link the existing model/tool libraries.

For every public construction action, the GUI dialog and JSON command adapter first populate a typed
tool command payload. `VToolCommandData` strips runtime document pointers; `PrepareToolCommand`
injects the cloned scene, document, data container, full-parse mode, and native GUI creation mode at
one boundary before calling the tool's static `Create`. This preserves Valentina output parameters
such as operation destination IDs. Tape and Puzzle actions follow the same native-model rule. No
handler may synthesize XML.

`scripts/check-valentina-coverage.py` fails when any `Create(Dialog)` implementation bypasses this
shared boundary or when a new Tool enum is neither constructible nor explicitly excluded. Native
tests replay every catalog action. A runtime adapter test sends identical Line, AlongLine, and EndLine
commands through the headless and actual dialog adapters and compares the complete saved construction
XML, including formulas, styles, notes, IDs, and history order.

`commands.preview` receives `project_root`, `change_set_id`, and `operations`. Native equivalence tests
may additionally select the `gui_dialog` construction adapter; production defaults to
`native_command`. The candidate path is
`.garmentcad/changesets/<change_set_id>/pattern/main.val`; `commands.commit` receives the same project
root and change-set ID and installs only that candidate.

The stable action list is `garmentcad.catalog.VALENTINA_TOOLS`; additions require an explicit catalog
review when updating the pinned Valentina commit.
