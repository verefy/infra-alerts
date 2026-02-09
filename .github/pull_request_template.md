## Goal

## Change Folder
`changes/<change-id>/`

## Verification
```bash
uv sync --frozen --extra dev
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -q
```

## Risk

## Rollback
See `changes/<change-id>/rollback.md`.

## Checklist
- [ ] `changes/<change-id>/` exists and all required docs are filled
- [ ] Verification commands executed (paste output or summarize failures)
- [ ] Rollback is plausible within minutes
