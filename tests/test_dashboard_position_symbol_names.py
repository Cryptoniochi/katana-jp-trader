from pathlib import Path

import pytest


TEMPLATE_DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "dashboard"
    / "templates"
)


@pytest.mark.parametrize(
    "template_name",
    [
        "dashboard.html",
        "mobile_dashboard.html",
    ],
)
def test_open_positions_use_embedded_symbol_name(
    template_name: str,
) -> None:
    content = (
        TEMPLATE_DIRECTORY / template_name
    ).read_text(encoding="utf-8")

    assert 'p.name??names[code]??""' in content
    assert (
        "const label=name?"
        "`${code} ${name}`:code;"
        in content
    )