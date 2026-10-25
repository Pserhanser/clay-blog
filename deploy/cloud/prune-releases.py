#!/usr/bin/env python3
"""Keep the active release and at most two rollback directories."""
import argparse
from pathlib import Path
import shutil


def prune(root: Path, previous: Path | None = None, apply: bool = False):
    root = root.resolve()
    releases = root / 'releases'
    current_link = root / 'current'
    if releases.is_symlink() or not releases.is_dir() or not current_link.is_symlink():
        raise ValueError('Expected releases directory and current symlink')
    active = current_link.resolve(strict=True)
    candidates = [item for item in releases.iterdir() if item.is_dir() and not item.is_symlink()]
    if active.parent != releases or active not in candidates:
        raise ValueError('Active release must be a direct child of releases')
    keep = {active}
    if previous:
        previous = previous.resolve()
        if previous.parent == releases and previous in candidates:
            keep.add(previous)
    for item in sorted(candidates, key=lambda path: path.stat().st_mtime_ns, reverse=True):
        if len(keep) >= 3:
            break
        keep.add(item)
    obsolete = [item for item in candidates if item not in keep]
    for item in obsolete:
        print(('Removing ' if apply else 'Would remove ') + str(item))
        if apply:
            shutil.rmtree(item)
    return obsolete


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--previous', type=Path)
    parser.add_argument('--apply', action='store_true', help='Default is dry-run')
    args = parser.parse_args()
    prune(args.root, args.previous, args.apply)
