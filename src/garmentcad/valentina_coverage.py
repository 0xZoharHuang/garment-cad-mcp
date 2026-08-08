from __future__ import annotations

import re
from pathlib import Path

from garmentcad.catalog import VALENTINA_CONSTRUCTION_TOOLS

NON_CONSTRUCTIBLE = {
    "Arrow": "GUI interaction mode, not a document object",
    "SinglePoint": "abstract tool category",
    "DoublePoint": "abstract tool category",
    "LinePoint": "abstract tool category",
    "AbstractSpline": "abstract tool category",
    "Cut": "abstract tool category",
    "NodePoint": "piece-path internal node type",
    "NodeArc": "piece-path internal node type",
    "NodeElArc": "piece-path internal node type",
    "NodeSpline": "piece-path internal node type",
    "NodeSplinePath": "piece-path internal node type",
    "BackgroundImage": "GUI background-image category",
    "BackgroundImageControls": "GUI interaction controls",
    "BackgroundPixmapImage": "GUI rendering implementation",
    "BackgroundSVGImage": "GUI rendering implementation",
}


def _function_body(text: str, declaration_start: int) -> str:
    opening = text.find("{", declaration_start)
    if opening < 0:
        raise ValueError("Cannot locate function body")
    depth = 0
    for position in range(opening, len(text)):
        if text[position] == "{":
            depth += 1
        elif text[position] == "}":
            depth -= 1
            if depth == 0:
                return text[declaration_start : position + 1]
    raise ValueError("Unterminated function body")


def gui_dialog_command_coverage(tools_root: Path) -> dict[str, dict[str, str]]:
    """Report whether every native GUI Create(Dialog) crosses the command DTO boundary."""
    result: dict[str, dict[str, str]] = {}
    declaration = re.compile(r"auto\s+(VTool[A-Za-z0-9_]+)::Create\(const QPointer<DialogTool>")
    for source in sorted(tools_root.rglob("*.cpp")):
        text = source.read_text(encoding="utf-8")
        for match in declaration.finditer(text):
            tool = match.group(1)
            body = _function_body(text, match.start())
            shared = any(
                marker in body
                for marker in (
                    "CreateToolFromCommand<",
                    "PrepareToolCommand(",
                    f"{tool}CommandData",
                )
            )
            result[tool] = {
                "status": "shared_command_dto" if shared else "direct_init_data",
                "source": str(source),
            }
    return result


def layout_export_formats(header: Path) -> dict[str, int]:
    """Read Valentina's explicitly numbered native export enum."""
    text = header.read_text(encoding="utf-8")
    match = re.search(r"enum class LayoutExportFormats[^\{]*\{(?P<body>.*?)\bCOUNT\b", text, re.S)
    if match is None:
        raise ValueError("Cannot locate LayoutExportFormats enum")
    result: dict[str, int] = {}
    for name, value in re.findall(r"\b([A-Z][A-Z0-9_]*)\s*=\s*(\d+)", match.group("body")):
        result[name] = int(value)
    return result


def enum_tools(header: Path) -> list[str]:
    text = header.read_text(encoding="utf-8")
    match = re.search(r"enum class Tool[^\{]*\{(?P<body>.*?)LAST_ONE_DO_NOT_USE", text, re.S)
    if match is None:
        raise ValueError("Cannot locate Valentina Tool enum")
    values = []
    for raw in match.group("body").split(","):
        name = raw.strip().split("//", 1)[0].strip()
        if name and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name):
            values.append(name)
    return values


def coverage(header: Path) -> dict[str, dict[str, str]]:
    constructible = set(VALENTINA_CONSTRUCTION_TOOLS)
    result = {}
    for tool in enum_tools(header):
        if tool in constructible:
            result[tool] = {"status": "constructible", "action": _action(tool)}
        elif tool in NON_CONSTRUCTIBLE:
            result[tool] = {"status": "excluded", "reason": NON_CONSTRUCTIBLE[tool]}
        else:
            result[tool] = {"status": "unmapped", "reason": "requires review"}
    return result


def _action(name: str) -> str:
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    return f"pattern.{snake}"
