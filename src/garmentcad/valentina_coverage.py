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
