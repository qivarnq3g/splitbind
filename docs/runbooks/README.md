# Runbooks

Reproducible multi-step operational procedures: deployment, migration, recovery, release, environment repair.

## What belongs here vs. in `docs/knowledge/`

| | `docs/runbooks/` | `docs/knowledge/` |
|---|---|---|
| Shape | Ordered steps someone executes | Facts, constraints, root causes |
| Question answered | "How do I do X?" | "Why does X behave that way?" |
| Test | Can be followed start to finish | Can be looked up mid-task |

A root cause discovered while writing a runbook goes to `docs/knowledge/`; the runbook links to it.

## Format

One procedure per file, named for the action (`restore-database-from-backup.md`, not `database.md`). Each file states:

1. **Preconditions** — required access, tools, and state.
2. **Steps** — exact commands with their working directory.
3. **Verification** — the command proving it worked and the expected output.
4. **Rollback** — how to undo it, or an explicit statement that it is irreversible.

A runbook whose steps have never been executed end to end is labelled as untested at the top.

<!-- BOOTSTRAP: Delete this file once real runbooks exist, or keep it as the directory convention note. -->
