from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

_META_PREFIXES = (".github/", ".os/")
_META_FILES = (".editorconfig", ".gitattributes", ".gitignore", "README.md")
_REQUIRED_CHANGE_FILES = (
    "acceptance.md",
    "assumptions.md",
    "design_contract.md",
    "eval_contract.md",
    "ops_contract.md",
    "options.md",
    "risk_register.md",
    "rollback.md",
    "spec.md",
)


@dataclass(frozen=True)
class _GitDiff:
    base: str
    head: str
    paths: tuple[str, ...]


def _run_git(args: list[str]) -> str:
    completed = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def _repo_root() -> Path:
    root = _run_git(["rev-parse", "--show-toplevel"]).strip()
    if root == "":
        raise RuntimeError("Failed to determine repo root via git.")
    return Path(root)


def _list_tree_paths(ref: str) -> tuple[str, ...]:
    out = _run_git(["ls-tree", "-r", "--name-only", ref]).strip()
    if out == "":
        return ()
    return tuple(line.strip() for line in out.splitlines() if line.strip() != "")


def _diff_paths(base: str, head: str) -> _GitDiff:
    if base == "" or head == "":
        raise RuntimeError("Missing --base/--head.")
    if base == "0" * 40:
        return _GitDiff(base=base, head=head, paths=_list_tree_paths(head))
    out = _run_git(["diff", "--name-only", f"{base}...{head}"]).strip()
    paths = () if out == "" else tuple(line.strip() for line in out.splitlines() if line.strip() != "")
    return _GitDiff(base=base, head=head, paths=paths)


def _is_meta_path(path: str) -> bool:
    if path in _META_FILES:
        return True
    return path.startswith(_META_PREFIXES)


def _change_ids_from_paths(paths: Iterable[str]) -> set[str]:
    ids: set[str] = set()
    for p in paths:
        parts = p.split("/")
        if len(parts) >= 2 and parts[0] == "changes":
            ids.add(parts[1])
    return ids


def _validate_change_folder(root: Path, change_id: str) -> list[str]:
    missing: list[str] = []
    base = root / "changes" / change_id
    for req in _REQUIRED_CHANGE_FILES:
        if not (base / req).is_file():
            missing.append(f"changes/{change_id}/{req}")
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args()

    root = _repo_root()
    diff = _diff_paths(base=args.base, head=args.head)

    substantive = [p for p in diff.paths if not _is_meta_path(p) and not p.startswith("changes/")]
    if len(substantive) == 0:
        return 0

    change_ids = _change_ids_from_paths(diff.paths)
    if len(change_ids) == 0:
        sys.stderr.write(
            "ERROR: Substantive changes detected but no changes/<change-id>/ docs were modified.\n"
            f"Base: {diff.base}\n"
            f"Head: {diff.head}\n"
            "Add a changes/<change-id>/ folder and include it in the same PR/commit.\n",
        )
        return 2

    missing: list[str] = []
    for change_id in sorted(change_ids):
        missing.extend(_validate_change_folder(root=root, change_id=change_id))

    if len(missing) != 0:
        sys.stderr.write("ERROR: Missing required change docs:\n")
        for m in missing:
            sys.stderr.write(f"- {m}\n")
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
