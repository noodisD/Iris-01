# docs.coverage

**What it means:** a module in `agent/` is not named in ARCHITECTURE.md, or a current document (README, ARCHITECTURE, CONTEXT, EXPLORATION_GUIDE, the frontend and Android READMEs, these runbooks) cites a path that no longer exists.

**Confirm:** `uv run python -m agent.doctor --only docs --json` lists the modules and paths under `details`.

**Safe fix:** add the module to the right row of ARCHITECTURE.md's subsystem table (a new subsystem gets a new row), or correct the path. If a module was deleted, remove its mention.

**Never:** satisfy the check by listing a module without saying what it is for. The check proves a module is named; whether the description is true still needs a reader.

See [README](README.md) for action classes and the rules every check follows.
