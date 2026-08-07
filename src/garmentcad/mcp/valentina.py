from mcp.server.fastmcp import FastMCP

from garmentcad.catalog import VALENTINA_TOOLS
from garmentcad.mcp.common import add_project_tools, register_atomic
from garmentcad.models import OperationDomain

mcp = FastMCP("valentina-cad")
add_project_tools(mcp, "valentina")
for tool_spec in VALENTINA_TOOLS:
    prefix = tool_spec.action.split(".", 1)[0]
    domain = {
        "pattern": OperationDomain.PATTERN,
        "measurement": OperationDomain.MEASUREMENTS,
        "layout": OperationDomain.LAYOUT,
        "export": OperationDomain.EXPORT,
    }.get(prefix, OperationDomain.PATTERN)
    register_atomic(mcp, tool_spec, domain)


def main() -> None:
    mcp.run(transport="stdio")
