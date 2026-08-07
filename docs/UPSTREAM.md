# Updating pinned upstream sources

Upstream revisions are machine-readable in `.upstream-revisions.json` and licensed in
`THIRD_PARTY.md`. Imports use squash/subtree commits so this repository remains a standalone local
Git repository without nested `.git` directories.

To update a component, fetch the candidate revision into a temporary clone, review its license and
API/tool-enum changes, then use `git subtree pull --prefix upstream/<name> <source> <revision> --squash`.
Update both revision records in the same commit. Run the Valentina coverage checker, regenerate JSON
Schemas, rebuild native/GUI targets, run upstream compatibility examples, and only then commit.

Never copy a working tree without its license, and never silently advance an upstream revision.
