import os

from mcp.server.fastmcp import FastMCP

from garmentcad.catalog import VALENTINA_TOOLS
from garmentcad.mcp.common import add_core_tools, register_atomic
from garmentcad.models import OperationDomain

mcp = FastMCP("valentina-cad")


def load_tools(names: set[str]) -> None:
    for tool_spec in VALENTINA_TOOLS:
        if tool_spec.name not in names:
            continue
        prefix = tool_spec.action.split(".", 1)[0]
        domain = {
            "pattern": OperationDomain.PATTERN,
            "measurement": OperationDomain.MEASUREMENTS,
            "layout": OperationDomain.LAYOUT,
            "export": OperationDomain.EXPORT,
        }.get(prefix, OperationDomain.PATTERN)
        register_atomic(mcp, tool_spec, domain)


add_core_tools(mcp, VALENTINA_TOOLS, load_tools)
if os.environ.get("GARMENTCAD_MCP_TOOL_MODE", "lazy").lower() == "eager":
    load_tools({tool_spec.name for tool_spec in VALENTINA_TOOLS})


def main() -> None:
    mcp.run(transport="stdio")
