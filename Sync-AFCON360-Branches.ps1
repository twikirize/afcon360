$ErrorActionPreference = "Stop"

$RepoPath = "C:\Users\OBED\Desktop\afcon360_app"
$Branches = @(
    "main",
    "feat/native-user-app-integration-20261108",
    "feat/native-driver-app-integration-20261108"
)
$WorkingBranch = "feat/native-user-app-integration-20261108"

if (-not (Test-Path -LiteralPath (Join-Path $RepoPath ".git"))) {
    throw "AFCON360 Git repository was not found at: $RepoPath"
}

Push-Location $RepoPath
$OriginalBranch = (& git branch --show-current).Trim()

function Invoke-Git {
    param([Parameter(Mandatory = $true)][string[]]$GitArgs)

    & git @GitArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Git command failed: git $($GitArgs -join ' ')"
    }
}

try {
    $StatusLines = @(& git status --porcelain)
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read Git working-tree status."
    }

    $TrackedChanges = @($StatusLines | Where-Object { $_ -notmatch '^\?\?' })
    if ($TrackedChanges.Count -gt 0) {
        Write-Host "Tracked files have changes:" -ForegroundColor Yellow
        $TrackedChanges | ForEach-Object { Write-Host "  $_" }
        throw "Synchronization stopped to protect tracked changes."
    }

    $UntrackedFiles = @(& git ls-files --others --exclude-standard)
    if ($LASTEXITCODE -ne 0) {
        throw "Could not identify untracked files."
    }

    if ($UntrackedFiles.Count -gt 0) {
        Write-Host "Preserving untracked local files:" -ForegroundColor Yellow
        $UntrackedFiles | ForEach-Object { Write-Host "  $_" }
    }

    $null = & git rev-parse --quiet --verify MERGE_HEAD 2>$null
    if ($LASTEXITCODE -eq 0) {
        throw "A Git merge is in progress. Finish or abort it before branch synchronization."
    }

    Write-Host "Fetching latest GitHub refs..." -ForegroundColor Cyan
    Invoke-Git -GitArgs @("fetch", "--prune", "origin")

    foreach ($Branch in $Branches) {
        foreach ($UntrackedFile in $UntrackedFiles) {
            $RemotePath = "origin/${Branch}:$UntrackedFile"
            & git cat-file -e $RemotePath 2>$null
            if ($LASTEXITCODE -eq 0) {
                throw "Untracked file would be overwritten on $Branch`: $UntrackedFile"
            }
        }
    }

    foreach ($Branch in $Branches) {
        $RemoteRef = "refs/remotes/origin/$Branch"
        $LocalRef = "refs/heads/$Branch"

        $null = & git show-ref --verify --quiet $RemoteRef 2>$null
        if ($LASTEXITCODE -ne 0) {
            throw "Remote branch origin/$Branch was not found. No reset or force update will be attempted."
        }

        $null = & git show-ref --verify --quiet $LocalRef 2>$null
        if ($LASTEXITCODE -eq 0) {
            Invoke-Git -GitArgs @("switch", $Branch)
        }
        else {
            Invoke-Git -GitArgs @("switch", "--track", "--create", $Branch, "origin/$Branch")
        }

        Write-Host "Fast-forwarding $Branch..." -ForegroundColor Cyan
        Invoke-Git -GitArgs @("pull", "--ff-only", "origin", $Branch)

        $Sha = (& git rev-parse --short HEAD).Trim()
        if ($LASTEXITCODE -ne 0) {
            throw "Could not read the updated commit for $Branch."
        }
        Write-Host "  $Branch -> $Sha" -ForegroundColor Green
    }

    Invoke-Git -GitArgs @("switch", $WorkingBranch)
    Write-Host ""
    Write-Host "Branch synchronization completed." -ForegroundColor Green
    Write-Host "IDE is now on: $WorkingBranch" -ForegroundColor Green
    Write-Host "main, User APK, and Driver APK local branches were fast-forwarded where possible."
    Write-Host "No force-push, reset, clean, or destructive operation was used."
    Write-Host ""
    Invoke-Git -GitArgs @("status", "--short", "--branch")
}
catch {
    if ($OriginalBranch) {
        Write-Host "Restoring the original branch ($OriginalBranch) after the sync was stopped..." -ForegroundColor Yellow
        & git switch $OriginalBranch | Out-Null
    }
    throw
}
finally {
    Pop-Location
}

