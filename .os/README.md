# Repo Operating System (.os)

This folder is the process glue: templates + a validator. It exists to prevent "agent-written chaos" by forcing
explicit intent, contracts, verification, and rollback for every change.

## Rule
Any substantive change must include a `changes/<change-id>/` folder in the same PR/commit and it must contain all
required docs.

## Create A Change Folder
Mac/Linux:
```bash
change_id="YYYY-MM-DD-short"
mkdir -p "changes/${change_id}"
cp .os/templates/*.md "changes/${change_id}/"
```

Windows PowerShell:
```powershell
$change_id = "YYYY-MM-DD-short"
New-Item -ItemType Directory -Force -Path "changes/$change_id" | Out-Null
Copy-Item ".os/templates/*.md" "changes/$change_id/"
```
