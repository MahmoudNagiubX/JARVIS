# Backup and restore

Backups use SQLite's online backup API and run an integrity check. They use
explicit paths, refuse accidental overwrite, and never invoke a shell.

```powershell
$env:PYTHONPATH = "src"
python -m jarvis --backup .\data\jarvis-backup.sqlite3
python -m jarvis --verify-backup .\data\jarvis-backup.sqlite3
python -m jarvis --restore-backup .\data\jarvis-backup.sqlite3 --restore-target .\data\jarvis-restore.sqlite3
```

Restore to a stopped runtime and a separate destination first. An existing
destination requires the explicit `--overwrite-restore` flag. Verify the
restored file before changing the deployment database path. Keep backups
access-controlled and outside source control; encryption and off-host storage
remain deployment responsibilities.
