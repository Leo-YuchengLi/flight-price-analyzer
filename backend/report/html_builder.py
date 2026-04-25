"""Render the Jinja2 HTML report template."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).parent / "templates"
CABIN_LABEL = {"Y": "经济舱", "W": "超级经济舱", "C": "商务舱", "F": "头等舱"}


def build_html(
    output_path: Path,
    flights: list[dict],
    matrix: dict[str, Any],
    stats: dict[str, Any],
    title: str,
) -> None:
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    tmpl = env.get_template("report.html.j2")

    html = tmpl.render(
        title=title,
        flights=flights,
        matrix=matrix,
        stats=stats,
        cabin_label=CABIN_LABEL.get(stats.get("cabin", ""), stats.get("cabin", "")),
    )
    output_path.write_text(html, encoding="utf-8")
