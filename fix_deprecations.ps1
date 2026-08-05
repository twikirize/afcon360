$projectRoot = "."
$files = Get-ChildItem -Path $projectRoot -Recurse -Include "*.py" | Where-Object { $_.FullName -notmatch "\\\.venv\\" -and $_.FullName -notmatch "\\migrations\\" }

foreach ($file in $files) {
    $content = Get-Content $file.FullName -Raw
    $original = $content
    $changed = $false

    # 1. Replace datetime.utcnow() calls (both as default= and direct calls)
    #    default=datetime.utcnow → default=lambda: datetime.now(timezone.utc)
    if ($content -match 'datetime\.utcnow') {
        $content = $content -replace 'default=datetime\.utcnow(?!\()', 'default=lambda: datetime.now(timezone.utc)'
        $content = $content -replace 'onupdate=datetime\.utcnow(?!\()', 'onupdate=lambda: datetime.now(timezone.utc)'
        $content = $content -replace 'datetime\.utcnow\(\)', 'datetime.now(timezone.utc)'
        # Ensure timezone import exists
        if ($content -match 'from datetime import datetime(?!, timezone)') {
            $content = $content -replace 'from datetime import datetime(?!, timezone)', 'from datetime import datetime, timezone'
        } elseif ($content -notmatch 'import datetime') {
            # If datetime is imported as module, add import timezone?
        }
        $changed = $true
    }

    # 2. Replace User.query.get(...) with db.session.get(User, ...)
    if ($content -match '\.query\.get\(') {
        $content = $content -replace '(\w+)\.query\.get\(([^)]+)\)', 'db.session.get($1, $2)'
        $changed = $true
    }

    if ($changed) {
        $bak = $file.FullName + ".bak"
        Copy-Item $file.FullName $bak
        Set-Content $file.FullName $content
        Write-Host "Updated $($file.FullName)"
    }
}
Write-Host "Done. .bak files are backups."