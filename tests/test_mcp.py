from garmentcad.catalog import GARMENTCODE_TOOLS, VALENTINA_TOOLS


def test_atomic_tool_names_are_unique():
    names = [tool.name for tool in (*GARMENTCODE_TOOLS, *VALENTINA_TOOLS)]
    assert len(names) == len(set(names))
    assert len(VALENTINA_TOOLS) >= 49
