# AGENTS.md (Repo Rules For Humans + Coding Agents)

This repo is set up for agent-driven development without turning into chaos. `main` is protected: ship via PRs.

## Non-Negotiables
- Never push to `main`. Always use a branch + Pull Request.
- If you change anything substantive, include `changes/<change-id>/` with all required docs (CI enforces this).
- Keep changes small. Split unrelated work into separate PRs / change-ids.
- Never commit secrets. Use GitHub Actions secrets / `.env` (untracked) + `.env.example` (tracked).
- `main` requires: PR and strict CI checks (your branch must be up-to-date with `main` before merge).

## What Counts As "Substantive"
| Example | Requires `changes/<change-id>/` |
|---|---|
| Code changes (anything outside `.github/`, `.os/`, `changes/`) | Yes |
| New docs outside `.os/` (e.g. `docs/`, `adr/`) | Yes |
| Workflow/process changes inside `.github/` / `.os/` | No |
| Root meta files (`README.md`, `.editorconfig`, `.gitattributes`, `.gitignore`) | No |

## Branch + PR Workflow (The Only Supported Way)
1. Sync `main`:
   - `git switch main`
   - `git pull --ff-only`
2. Create a branch:
   - `git switch -c codex/<change-id>-<short-slug>`
3. If substantive: create change docs (see `.os/README.md`).
4. Implement the change.
5. Verify locally:
   - `uv sync --frozen --extra dev`
   - `uv run ruff check .`
   - `uv run ruff format --check .`
   - `uv run mypy`
   - `uv run pytest -q`
6. Commit (Conventional Commits):
   - `git add -p`
   - `git commit -m "feat: <imperative summary>"`
7. Push branch + open PR:
   - `git push -u origin HEAD`
   - `gh pr create --fill` (or GitHub UI)
8. Required checks must be green before merge:
   - `os-validate`
   - `python-checks`
9. Merge: squash merge, delete branch.

## Strict Status Checks: What You Do When Your Branch Is Behind `main`
If GitHub says your PR is out-of-date with `main`, update your branch:
```bash
git fetch origin
git merge origin/main
git push
```

## Infra-Alerts Specific: State Branch
- The monitor workflow persists state to the `state` branch (not `main`).
- Do not protect the `state` branch with PR-required rules (Actions must be able to push).
- The only workflow that should need write permissions is `.github/workflows/monitor.yml` (`permissions: contents: write`).

## Change Folder Contract
- `change-id` format: `YYYY-MM-DD-short`
- Create it by copying templates:
  - Mac/Linux: `mkdir -p changes/<change-id> && cp .os/templates/*.md changes/<change-id>/`
  - Windows PowerShell: `New-Item -ItemType Directory -Force -Path changes/<change-id>; Copy-Item .os/templates/*.md changes/<change-id>/`
- The PR must include `changes/<change-id>/` in the same diff as the substantive code change.
