[CmdletBinding()]
param(
    [ValidateSet("List", "ArchiveBranch", "ArchiveStash", "RestoreBranch", "RestoreStash")]
    [string]$Action = "List",
    [string]$BranchName,
    [string]$StashSelector,
    [string]$ArchiveRef
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$ProtectedBranches = @(
    "main",
    "master",
    "develop",
    "feat/native-user-app-integration-20261108",
    "feat/native-driver-app-integration-20261108"
)

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)][string[]]$GitArgs,
        [switch]$AllowFailure
    )
    # Windows PowerShell 5.1 can promote redirected native stderr (including
    # normal Git progress such as "From https://...") to ErrorRecords. With
    # ErrorActionPreference=Stop those benign messages terminate the script
    # before Git's exit code can be checked. Temporarily use Continue while
    # capturing both streams; the actual Git exit code remains authoritative.
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = @(& git @GitArgs 2>&1 | ForEach-Object { [string]$_ })
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($code -ne 0 -and -not $AllowFailure) {
        $details = ($output | ForEach-Object { "$_" }) -join [System.Environment]::NewLine
        throw (("git {0} failed (exit {1})." -f ($GitArgs -join " "), $code) + [System.Environment]::NewLine + $details)
    }
    return $output
}

function Test-GitRef {
    param([Parameter(Mandatory = $true)][string]$RefName)
    & git show-ref --verify --quiet $RefName 2>$null
    return ($LASTEXITCODE -eq 0)
}

function Get-GitRefSha {
    param([Parameter(Mandatory = $true)][string]$RefName)
    $value = @(& git rev-parse --verify $RefName 2>$null)
    if ($LASTEXITCODE -eq 0 -and $value.Count -gt 0) {
        return ([string]$value[0]).Trim()
    }
    return $null
}

function Assert-Repository {
    $null = Invoke-Git -GitArgs @("rev-parse", "--show-toplevel")
    $null = Invoke-Git -GitArgs @("remote", "get-url", "origin")
}

function Assert-CleanWorkingTree {
    $changes = @(& git status --porcelain)
    if ($changes.Count -gt 0) {
        $details = ($changes -join [System.Environment]::NewLine)
        throw ("Working tree is not clean. Commit or stash these changes first:" + [System.Environment]::NewLine + $details)
    }
}

function Assert-NotProtected {
    param([Parameter(Mandatory = $true)][string]$Name)
    if ($ProtectedBranches -contains $Name -or
        $Name.StartsWith("archive/", [System.StringComparison]::OrdinalIgnoreCase) -or
        $Name.StartsWith("release/", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to archive or overwrite protected branch '$Name'."
    }
}

function Get-ArchiveTagName {
    param(
        [Parameter(Mandatory = $true)][string]$Kind,
        [Parameter(Mandatory = $true)][string]$Name
    )
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $safeName = ($Name -replace '[^A-Za-z0-9._-]+', '-').Trim('-')
    if ([string]::IsNullOrWhiteSpace($safeName)) { $safeName = "unnamed" }
    if ($safeName.Length -gt 64) { $safeName = $safeName.Substring(0, 64) }
    return "archive/$Kind/$stamp/$safeName"
}

function Publish-ArchiveTag {
    param(
        [Parameter(Mandatory = $true)][string]$TagName,
        [Parameter(Mandatory = $true)][string]$CommitSha,
        [Parameter(Mandatory = $true)][string]$Message
    )
    if (Test-GitRef -RefName ("refs/tags/" + $TagName)) {
        throw "Archive tag already exists locally: $TagName"
    }

    $null = Invoke-Git -GitArgs @("check-ref-format", ("refs/tags/" + $TagName))
    $null = Invoke-Git -GitArgs @("tag", "-a", $TagName, $CommitSha, "-m", $Message)
    $null = Invoke-Git -GitArgs @("push", "origin", ("refs/tags/" + $TagName))

    $remoteTag = @(& git ls-remote --exit-code --tags origin ("refs/tags/" + $TagName) 2>$null)
    if ($LASTEXITCODE -ne 0 -or $remoteTag.Count -eq 0) {
        throw "Archive tag was not confirmed on origin. Original data has not been deleted. Local tag: $TagName"
    }
}

function Confirm-DestructiveStep {
    param(
        [Parameter(Mandatory = $true)][string]$Prompt,
        [Parameter(Mandatory = $true)][string]$RequiredWord
    )
    Write-Host ""
    Write-Host $Prompt -ForegroundColor Yellow
    $answer = Read-Host ("Type {0} to continue" -f $RequiredWord)
    return ($answer -ceq $RequiredWord)
}

function Show-ArchiveInventory {
    $null = Invoke-Git -GitArgs @("fetch", "origin", "--prune", "--tags")

    Write-Host ""
    Write-Host "AFCON360 branch archive tags" -ForegroundColor Cyan
    $branchTags = @(& git tag --list "archive/branches/*" --sort=-creatordate)
    if ($branchTags.Count -eq 0) { Write-Host "  (none)" }
    else { $branchTags | ForEach-Object { Write-Host ("  " + $_) } }

    Write-Host ""
    Write-Host "AFCON360 stash archive tags" -ForegroundColor Cyan
    $stashTags = @(& git tag --list "archive/stashes/*" --sort=-creatordate)
    if ($stashTags.Count -eq 0) { Write-Host "  (none)" }
    else { $stashTags | ForEach-Object { Write-Host ("  " + $_) } }

    Write-Host ""
    Write-Host "Current stash list" -ForegroundColor Cyan
    $stashList = @(& git stash list --date=local)
    if ($stashList.Count -eq 0) { Write-Host "  (none)" }
    else { $stashList | ForEach-Object { Write-Host ("  " + $_) } }

    Write-Host ""
    Write-Host "Local branches" -ForegroundColor Cyan
    @(& git branch -vv) | ForEach-Object { Write-Host ("  " + $_) }

    Write-Host ""
    Write-Host "Remote branches" -ForegroundColor Cyan
    @(& git branch -r) | ForEach-Object { Write-Host ("  " + $_) }
}

function Archive-Branch {
    if ([string]::IsNullOrWhiteSpace($BranchName)) {
        throw "Supply -BranchName with the exact branch name."
    }

    Assert-CleanWorkingTree
    $null = Invoke-Git -GitArgs @("fetch", "origin", "--prune")
    Assert-NotProtected -Name $BranchName
    $null = Invoke-Git -GitArgs @("check-ref-format", "--branch", $BranchName)

    $current = (& git branch --show-current).Trim()
    if ($current -eq $BranchName) {
        throw "The branch '$BranchName' is currently checked out. Switch to main or another branch first."
    }

    $localSha = Get-GitRefSha -RefName ("refs/heads/" + $BranchName)
    $remoteSha = Get-GitRefSha -RefName ("refs/remotes/origin/" + $BranchName)
    if (-not $localSha -and -not $remoteSha) {
        throw "Neither local branch nor origin/$BranchName exists."
    }

    $versions = @()
    if ($localSha) {
        $versions += [pscustomobject]@{ Label = "local"; Sha = $localSha }
    }
    if ($remoteSha -and $remoteSha -ne $localSha) {
        $versions += [pscustomobject]@{ Label = "remote"; Sha = $remoteSha }
    }
    elseif ($remoteSha -and -not $localSha) {
        $versions += [pscustomobject]@{ Label = "remote"; Sha = $remoteSha }
    }

    $tagBase = Get-ArchiveTagName -Kind "branches" -Name $BranchName
    $createdTags = @()
    foreach ($version in $versions) {
        $tagName = $tagBase
        if ($versions.Count -gt 1) {
            $tagName = $tagBase + "-" + $version.Label
        }

        $message = "AFCON360 archived branch ref '$BranchName' ($($version.Label)); original commit $($version.Sha)."
        Publish-ArchiveTag -TagName $tagName -CommitSha $version.Sha -Message $message
        $createdTags += $tagName
        Write-Host ("Verified remote archive tag: " + $tagName) -ForegroundColor Green
    }

    Write-Host ""
    Write-Host "The branch history is preserved on origin as:" -ForegroundColor Green
    $createdTags | ForEach-Object { Write-Host ("  " + $_) }

    $prompt = "This will delete '$BranchName' from origin (if present) and the local repository (if present). Archive tags will remain."
    if (-not (Confirm-DestructiveStep -Prompt $prompt -RequiredWord "DELETE")) {
        Write-Host "Cancelled. Original branch refs are unchanged; archive tag(s) remain."
        return
    }

    if ($remoteSha) {
        $remoteNow = @(& git ls-remote --heads origin ("refs/heads/" + $BranchName) 2>$null)
        $remoteNowSha = $null
        if ($remoteNow.Count -gt 0) {
            $remoteNowSha = $remoteNow[0].Split([char[]]@(9, 32), [System.StringSplitOptions]::RemoveEmptyEntries)[0]
        }
        if ($remoteNowSha -ne $remoteSha) {
            throw "origin/$BranchName changed after the archive snapshot. It was NOT deleted; archive tag(s) remain."
        }

        $null = Invoke-Git -GitArgs @("push", "origin", "--delete", $BranchName)
        Write-Host ("Deleted origin/" + $BranchName)
    }

    if ($localSha) {
        $null = Invoke-Git -GitArgs @("branch", "-D", $BranchName)
        Write-Host ("Deleted local branch " + $BranchName)
    }

    Write-Host "Branch archived and original ref(s) removed." -ForegroundColor Green
}

function Archive-Stash {
    Assert-CleanWorkingTree
    if ([string]::IsNullOrWhiteSpace($StashSelector) -or
        $StashSelector -notmatch '^stash@\{\d+\}$') {
        throw "Supply an exact stash selector such as -StashSelector 'stash@{2}'."
    }

    $stashRef = "{0}^{{commit}}" -f $StashSelector
    $stashSha = Get-GitRefSha -RefName $stashRef
    if (-not $stashSha) {
        throw "Could not resolve $StashSelector. Refresh git stash list and try again."
    }

    $subject = (& git log -1 --format=%s $stashSha).Trim()
    $tagName = Get-ArchiveTagName -Kind "stashes" -Name $subject
    $message = "AFCON360 archived $StashSelector. Stash commit $stashSha. The tag preserves all parents, including index and untracked-file snapshots."

    Publish-ArchiveTag -TagName $tagName -CommitSha $stashSha -Message $message
    Write-Host ("Verified remote stash archive tag: " + $tagName) -ForegroundColor Green
    Write-Host ("Saved stash commit: " + $stashSha)

    $prompt = "The complete stash commit is preserved by the verified remote tag. This removes $StashSelector from the active local stash list only."
    if (-not (Confirm-DestructiveStep -Prompt $prompt -RequiredWord "DROP")) {
        Write-Host "Cancelled. Original stash remains in the stash list; archive tag is available."
        return
    }

    $null = Invoke-Git -GitArgs @("stash", "drop", $StashSelector)
    Write-Host "Stash removed from active list; archived tag remains recoverable." -ForegroundColor Green
}

function Restore-Branch {
    if ([string]::IsNullOrWhiteSpace($ArchiveRef) -or [string]::IsNullOrWhiteSpace($BranchName)) {
        throw "Supply both -ArchiveRef and -BranchName."
    }

    $tagRef = "refs/tags/" + $ArchiveRef
    if (-not (Test-GitRef -RefName $tagRef)) {
        $null = Invoke-Git -GitArgs @("fetch", "origin", "--tags")
    }
    $sha = Get-GitRefSha -RefName ($tagRef + "^{commit}")
    if (-not $sha) {
        throw "Archive tag not found: $ArchiveRef"
    }

    Assert-NotProtected -Name $BranchName
    $null = Invoke-Git -GitArgs @("check-ref-format", "--branch", $BranchName)
    if ((Test-GitRef -RefName ("refs/heads/" + $BranchName)) -or
        (Test-GitRef -RefName ("refs/remotes/origin/" + $BranchName))) {
        throw "A local or remote branch named '$BranchName' already exists. Nothing was overwritten."
    }

    $null = Invoke-Git -GitArgs @("branch", $BranchName, $sha)
    $null = Invoke-Git -GitArgs @("push", "-u", "origin", ("refs/heads/" + $BranchName + ":refs/heads/" + $BranchName))
    Write-Host ("Restored branch '$BranchName' from " + $ArchiveRef) -ForegroundColor Green
}

function Restore-Stash {
    if ([string]::IsNullOrWhiteSpace($ArchiveRef)) {
        throw "Supply -ArchiveRef with the exact archive/stashes/... tag."
    }

    $tagRef = "refs/tags/" + $ArchiveRef
    if (-not (Test-GitRef -RefName $tagRef)) {
        $null = Invoke-Git -GitArgs @("fetch", "origin", "--tags")
    }
    $sha = Get-GitRefSha -RefName ($tagRef + "^{commit}")
    if (-not $sha) {
        throw "Archive tag not found: $ArchiveRef"
    }

    $existing = @(& git stash list --format=%H)
    if ($existing -contains $sha) {
        Write-Host "This exact stash commit is already present in the active stash list. No duplicate was created."
        @(& git stash list --date=local) | ForEach-Object { Write-Host $_ }
        return
    }

    $null = Invoke-Git -GitArgs @("stash", "store", "-m", ("Restored from archive tag " + $ArchiveRef), $sha)
    Write-Host "The archived stash is back in the active stash list; it has NOT been applied to the working tree." -ForegroundColor Green
    @(& git stash list -n 1 --date=local) | ForEach-Object { Write-Host ("  " + $_) }
    Write-Host "Inspect it first; use git stash apply to restore its files without deleting the stash."
}

try {
    Assert-Repository
    switch ($Action) {
        "List" { Show-ArchiveInventory }
        "ArchiveBranch" { Archive-Branch }
        "ArchiveStash" { Archive-Stash }
        "RestoreBranch" { Restore-Branch }
        "RestoreStash" { Restore-Stash }
    }
}
catch {
    Write-Error $_
    exit 1
}
