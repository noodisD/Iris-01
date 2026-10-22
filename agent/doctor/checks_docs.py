"""Do the docs still describe the code? Drift found once by audit, now by check.

An audit on 2026-10-22 found the README and both architecture documents a month
behind the code: whole subsystems undescribed, a fixed bug still recommended,
two decisions silently reversed. This check keeps the cheap half of that audit:
every module is named in ARCHITECTURE.md, and no current document points at a
file that is gone. Whether the prose is still true needs a reader.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import Result, check

ROOT = Path(__file__).resolve().parents[2]
#: Documents meant to describe the system as it is. ADRs are dated records and
#: may name files that later moved; they are not checked.
CURRENT_DOCS = ("README.md", "ARCHITECTURE.md", "CONTEXT.md", "EXPLORATION_GUIDE.md",
                "frontend/README.md", "android/README.md", "docs/runbooks/*.md")
_PATH = re.compile(r"`((?:agent|scripts|migrations|docs|frontend/src|prompts|tests)/[\w./*-]+?)`")


def scan(root: Path = ROOT) -> tuple[list[str], list[str]]:
    """Modules ARCHITECTURE.md never names, and paths current docs cite that do not exist."""
    architecture = (root / "ARCHITECTURE.md").read_text() if (root / "ARCHITECTURE.md").exists() else ""
    unnamed = []
    for module in sorted((root / "agent").rglob("*.py")):
        relative = module.relative_to(root / "agent")
        if module.name in ("__init__.py", "__main__.py") or "tests" in relative.parts:
            continue
        package = f"{relative.parts[0]}/*" if len(relative.parts) > 1 else None
        if module.name not in architecture and str(relative) not in architecture \
                and not (package and package in architecture):
            unnamed.append(str(relative))
    broken = []
    for pattern in CURRENT_DOCS:
        for doc in sorted(root.glob(pattern)):
            for cited in sorted(set(_PATH.findall(doc.read_text()))):
                # NNNN and <name> are placeholders for any file of that shape.
                target = re.sub(r"N{3,}", "*", cited.rstrip("."))
                if "*" in target or "<" in target:
                    if not list(root.glob(target.replace("<", "*").replace(">", ""))):
                        broken.append(f"{doc.relative_to(root)}: {cited}")
                elif not (root / target).exists():
                    broken.append(f"{doc.relative_to(root)}: {cited}")
    return unnamed, broken


@check("docs.coverage", "docs")
def coverage() -> Result:
    unnamed, broken = scan()
    total = len(unnamed) + len(broken)
    details = {"unnamed_modules": unnamed[:30], "broken_paths": broken[:30]}
    if total == 0:
        return Result("docs.coverage", "ok", "ARCHITECTURE.md names every module and no doc cites a missing file.",
                      value=0, expected="0", details=details)
    parts = ([f"{len(unnamed)} module(s) unnamed in ARCHITECTURE.md"] if unnamed else []) + \
            ([f"{len(broken)} cited path(s) missing"] if broken else [])
    return Result("docs.coverage", "warn", "; ".join(parts) + ".", value=total, expected="0", details=details,
                  causes=["A module was added or moved without updating ARCHITECTURE.md.",
                          "A file was renamed or deleted while a document still points at it."],
                  action="Name the module in ARCHITECTURE.md's subsystem table, or fix the path.",
                  action_class="safe-auto")
