"""Project KATANAのJ-Quants依存を棚卸しする。"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path


SEARCH_TERMS = (
    "JQuants",
    "jquants",
    "JQUANTS_API_KEY",
    "jquants-current-day",
    "previous-day-replay",
    "JQuantsMinuteDownloader",
)

EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    "data",
    "logs",
    "reports",
    "archive",
    ".pytest_cache",
}

TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".toml",
    ".json",
    ".yaml",
    ".yml",
    ".ps1",
    ".cmd",
}


@dataclass(frozen=True, slots=True)
class DependencyHit:
    path: str
    line_number: int
    term: str
    line: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("reports/jquants_dependency_audit.json"),
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=Path("reports/jquants_dependency_audit.md"),
    )
    return parser.parse_args()


def should_scan(path: Path) -> bool:
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return False
    return not any(part in EXCLUDED_PARTS for part in path.parts)


def scan(root: Path) -> list[DependencyHit]:
    hits: list[DependencyHit] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue

        relative = path.relative_to(root)
        if not should_scan(relative):
            continue

        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            try:
                lines = path.read_text(
                    encoding="utf-8-sig"
                ).splitlines()
            except UnicodeDecodeError:
                continue

        for line_number, line in enumerate(lines, start=1):
            for term in SEARCH_TERMS:
                if term.lower() in line.lower():
                    hits.append(
                        DependencyHit(
                            path=str(relative),
                            line_number=line_number,
                            term=term,
                            line=line.strip(),
                        )
                    )

    return hits


def classify(hit: DependencyHit) -> str:
    path = hit.path.lower()
    line = hit.line.lower()

    if path.startswith("tests/"):
        return "test"
    if path.startswith("docs/") or path.endswith(".md"):
        return "documentation"
    if (
        "jquantsminute" in line
        or "jquants_downloader" in line
        or "jquants-current-day" in line
    ):
        return "runtime"
    if "previous-day-replay" in line:
        return "replay"
    if "jquants_api_key" in line:
        return "configuration"
    return "other"


def render_markdown(
    root: Path,
    hits: list[DependencyHit],
) -> str:
    counts = Counter(classify(hit) for hit in hits)
    runtime_hits = [
        hit
        for hit in hits
        if classify(hit)
        in {"runtime", "replay", "configuration"}
    ]

    lines = [
        "# Project KATANA J-Quants Dependency Audit",
        "",
        f"- Project root: `{root}`",
        f"- Total hits: **{len(hits)}**",
        "",
        "## Summary",
        "",
    ]

    for category in (
        "runtime",
        "replay",
        "configuration",
        "test",
        "documentation",
        "other",
    ):
        lines.append(f"- {category}: {counts.get(category, 0)}")

    lines.extend(["", "## Runtime-impacting dependencies", ""])

    if not runtime_hits:
        lines.append(
            "No runtime-impacting J-Quants dependencies were found."
        )
    else:
        for hit in runtime_hits:
            lines.append(
                f"- `{hit.path}:{hit.line_number}` "
                f"[{classify(hit)}] `{hit.line}`"
            )

    lines.extend(["", "## All matches", ""])

    for hit in hits:
        lines.append(
            f"- `{hit.path}:{hit.line_number}` "
            f"[{classify(hit)} / {hit.term}] `{hit.line}`"
        )

    lines.extend(
        [
            "",
            "## Decision guide",
            "",
            "- Light can be cancelled only after all runtime, "
            "replay, and configuration hits are removed or replaced.",
            "- Test and documentation hits alone do not require an "
            "active J-Quants subscription.",
            "",
        ]
    )

    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    hits = scan(root)

    json_output = (
        args.json_output
        if args.json_output.is_absolute()
        else root / args.json_output
    )
    markdown_output = (
        args.markdown_output
        if args.markdown_output.is_absolute()
        else root / args.markdown_output
    )

    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)

    json_output.write_text(
        json.dumps(
            [asdict(hit) for hit in hits],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    markdown_output.write_text(
        render_markdown(root, hits),
        encoding="utf-8",
    )

    counts = Counter(classify(hit) for hit in hits)
    impact_count = sum(
        counts.get(key, 0)
        for key in ("runtime", "replay", "configuration")
    )

    print("J-Quants dependency audit completed.")
    print(f"Total hits: {len(hits)}")
    print(f"Runtime-impacting hits: {impact_count}")
    print(f"Markdown: {markdown_output}")
    print(f"JSON: {json_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
