"""Stage only application sources for Wrangler's recursive module scan.

The entrypoint stays at worker.py; vendored packages stay at python_modules/.
No virtual environments, tests, secrets, or project tooling enter base_dir.
"""

import argparse
from pathlib import Path
import shutil
import sys

try:
    from scripts.check_worker_bundle import load_config
except ModuleNotFoundError:  # Running this file directly from the CLI.
    from check_worker_bundle import load_config


def prepare_source_tree(root: Path) -> Path:
    root = root.resolve()
    config = load_config(root / "wrangler.jsonc")
    target = root / config.get("base_dir", "")
    expected = root / ".cache" / "worker-source"
    # Validate resolved absolute paths before removing any generated directory.
    if target.resolve() != expected or not target.resolve().is_relative_to(root):
        raise ValueError("base_dir must be the workspace's .cache/worker-source directory")
    source = root / "app"
    if not source.is_dir() or source.is_symlink() or not (root / config["main"]).is_file():
        raise ValueError("Application source directory or Worker entrypoint is missing")
    if any(p.is_symlink() for p in source.rglob("*")):
        raise ValueError("Symlinks are not supported in staged application sources")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    shutil.copytree(source, target / "app", ignore=shutil.ignore_patterns(
        "__pycache__", "*.pyc", "*.pyo", ".*"))
    print(f"Staged application sources in {target.relative_to(root)}")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        prepare_source_tree(args.root)
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"Cannot stage Worker sources: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
