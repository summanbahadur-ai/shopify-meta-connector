"""Inspect actual vendored files against a conservative upload-part budget.

950 is a project guard, not a documented Cloudflare hard limit. Review Wrangler's
dry-run output for the final bundle. No credentials or network access required.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys


def load_config(path: Path) -> dict:
    """Support JSONC comments and trailing commas, preserving quoted strings."""
    source = path.read_text(encoding="utf-8-sig")
    source = re.sub(r'"(?:\\.|[^"\\])*"|//[^\r\n]*|/\*[\s\S]*?\*/',
                    lambda m: m[0] if m[0].startswith('"') else " ", source)
    source = re.sub(r'"(?:\\.|[^"\\])*"|,\s*(?=[}\]])',
                    lambda m: m[0] if m[0].startswith('"') else "", source)
    return json.loads(source)


def matches(path: str, pattern: str) -> bool:
    """Implement this project's *, ** and ? exclusion patterns; reject others."""
    if any(char in pattern for char in "[]{}\\"):
        raise ValueError(f"Unsupported exclusion glob: {pattern}")
    tokens = re.findall(r"\*\*/|\*\*|\*|\?|.", pattern)
    expressions = {"**/": "(?:.*/)?", "**": ".*", "*": "[^/]*", "?": "[^/]"}
    return re.fullmatch("".join(expressions.get(token, re.escape(token)) for token in tokens), path) is not None


def check_bundle(root: Path) -> int:
    config = load_config(root / "wrangler.jsonc")
    vendor = root / "python_modules"
    files = sorted(path.relative_to(vendor).as_posix() for path in vendor.rglob("*") if path.is_file())
    if not files:
        print("python_modules is missing or empty; run uv run pywrangler sync first.", file=sys.stderr)
        return 1
    patterns = config.get("python_modules", {}).get("exclude", ["**/*.pyc"])
    included = [path for path in files if not any(matches(path, pattern) for pattern in patterns)]
    counts = Counter(path.split("/", 1)[0] for path in included)
    app_count = sum(1 for path in (root / "app").rglob("*.py") if path.is_file())
    entry_count = int((root / config["main"]).is_file())
    estimated = len(included) + app_count + entry_count + 16
    print(f"Vendor files: raw={len(files)} excluded={len(files) - len(included)} included={len(included)}")
    for package, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        print(f"  {package}: {count}")
    print(f"Application={app_count} entrypoint={entry_count} reserve=16 estimated_parts={estimated}")
    print("Conservative project budget: estimated_parts < 950; not a documented Cloudflare hard limit.")
    if estimated >= 950:
        print("Upload-part budget exceeded; review dependencies and Wrangler dry-run output.", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        return check_bundle(args.root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Cannot inspect worker bundle: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
