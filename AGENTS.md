# Quant-Forge agent instructions

This file is the single source of truth for repository instructions. Keep agent-specific entrypoints such as `CLAUDE.md` as thin references to this file instead of duplicating these rules.

## Repository overview

- `backend/`: Python backend service built with FastAPI.
- `frontend/`: frontend application (currently minimal; inspect the directory before assuming its tooling).
- `mobile/`: mobile application (currently minimal; inspect the directory before assuming its tooling).
- `scripts/`: repository-level development scripts.

Read the relevant directory README and configuration files before making changes in that area.

## Working rules

- Preserve the existing structure and conventions unless the task requires a change.
- Keep changes focused on the requested outcome. Do not add dependencies, generated files, or broad refactors without a clear need.
- Never commit secrets, credentials, tokens, local virtual environments, build output, or machine-specific settings.
- Prefer small, readable functions and clear names. Match the surrounding code style.
- Update the relevant README or documentation when a command, public behavior, or setup step changes.
- Before editing, check `git status` and avoid overwriting unrelated user changes.

## Backend commands

Run these from `backend/` unless noted otherwise:

```powershell
# Start the development server from the repository root
.\scripts\dev.ps1

# Or start it directly from backend/
uv run uvicorn main:app --reload

# Format Python code
uv run --group dev isort .
uv run --group dev black .

# Run tests when the change affects backend behavior
uv run --group dev pytest
```

The backend targets Python 3.12 or newer. Black and isort use a line length of 120 and Black-compatible import ordering.

## Validation

- For backend changes, run the most relevant tests and formatters that are available.
- For documentation-only changes, verify Markdown links, code blocks, and commands against the current repository.
- Report which checks were run and call out checks that could not be run.

## Git and delivery

- Do not rewrite history, reset, or discard user changes unless explicitly requested.
- Do not create commits unless the user asks for one.
- In the final response, summarize changed files, validation performed, and any remaining limitation.
