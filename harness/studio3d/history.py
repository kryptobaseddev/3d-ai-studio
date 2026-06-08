"""studio3d.history — git-tracked, point-in-time history of generated designs.

Design decisions (per the council verdict):
- **Isolated store**: an independent git repository whose work-tree is `output/`
  but whose git dir is `output/.studio3d-history`. It never creates a `.git` at the
  project root and never touches the user's own VCS.
- **One evolving bundle, no version spam**: regenerating the same design overwrites
  the same `output/<slug>/` folder; each change is captured as a *commit*, so you
  get point-in-time recovery without a pile of `-001/-002/...` folders. A separate
  variant is created only when the user explicitly asks (`--variant`).
"""
from __future__ import annotations

import os
import subprocess

GITDIR_NAME = ".studio3d-history"


def _gitdir(output_root: str) -> str:
    return os.path.join(os.path.abspath(output_root), GITDIR_NAME)


def _git(output_root: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    gitdir = _gitdir(output_root)
    cmd = ["git", f"--git-dir={gitdir}", f"--work-tree={os.path.abspath(output_root)}", *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def ensure_repo(output_root: str) -> str:
    """Init the isolated history repo if missing. Returns the git dir."""
    gitdir = _gitdir(output_root)
    if not os.path.isdir(gitdir):
        subprocess.run(["git", "init", "--quiet", f"--separate-git-dir={gitdir}",
                        "--initial-branch=main", os.path.abspath(output_root)],
                       capture_output=True, text=True)
        # initializing with --separate-git-dir leaves a .git FILE in output_root;
        # remove it so it can never be confused with a real repo by other tools.
        dotgit = os.path.join(output_root, ".git")
        if os.path.isfile(dotgit):
            os.remove(dotgit)
        # exclude the history gitdir + the rendered web copy from itself
        info = os.path.join(gitdir, "info")
        os.makedirs(info, exist_ok=True)
        with open(os.path.join(info, "exclude"), "w") as f:
            f.write(f"{GITDIR_NAME}/\n")
        _git(output_root, "config", "user.email", "studio3d@local", check=False)
        _git(output_root, "config", "user.name", "studio3d", check=False)
        _git(output_root, "config", "commit.gpgsign", "false", check=False)
    return gitdir


def commit_bundle(bundle_dir: str, message: str) -> str | None:
    """Stage and commit a single bundle (the evolving design). Returns the commit
    SHA, or None if there was nothing to commit."""
    output_root = os.path.dirname(os.path.abspath(bundle_dir))
    ensure_repo(output_root)
    rel = os.path.relpath(bundle_dir, output_root)
    _git(output_root, "add", "--", rel, "manifest.json", check=False)
    # only commit if the index changed for this bundle
    status = _git(output_root, "status", "--porcelain", "--", rel, check=False)
    staged = _git(output_root, "diff", "--cached", "--name-only", check=False).stdout.strip()
    if not staged:
        return None
    res = _git(output_root, "commit", "--quiet", "-m", message, check=False)
    if res.returncode != 0:
        return None
    sha = _git(output_root, "rev-parse", "HEAD", check=False).stdout.strip()
    return sha


def history(output_root: str, bundle: str | None = None, limit: int = 20) -> list[dict]:
    """Commit log (optionally scoped to one bundle)."""
    ensure_repo(output_root)
    args = ["log", f"-{limit}", "--pretty=format:%H\t%ci\t%s"]
    if bundle:
        args += ["--", bundle]
    res = _git(output_root, *args, check=False)
    out = []
    for line in res.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            out.append({"sha": parts[0], "date": parts[1], "message": parts[2]})
    return out


def revert_bundle(output_root: str, bundle: str, sha: str) -> bool:
    """Restore a bundle's files to a past commit (point-in-time recovery).
    Operates in place — the recovered state becomes the current bundle, and the
    recovery itself is committed, preserving forward history."""
    ensure_repo(output_root)
    res = _git(output_root, "checkout", sha, "--", bundle, check=False)
    if res.returncode != 0:
        return False
    commit_bundle(os.path.join(output_root, bundle), f"revert {bundle} to {sha[:8]}")
    return True
