# AFCON360 Git archive and recovery

Use scripts/git/afcon360-git-archive.ps1 to move completed branches and obsolete stash entries out of the active lists without destroying their history. The helper supports Windows PowerShell 5.1; normal Git stderr progress output is captured and judged by Git's exit code rather than treated as a terminating PowerShell error. Missing local or remote branch refs are treated as an expected absent ref, allowing local-only and remote-only branches to be archived independently.

## Inspect first

Run from the repository root:

    .\scripts\git\afcon360-git-archive.ps1

This lists local and remote branches, current stashes and archive tags.

## Archive a completed branch

Only archive a branch after confirming its pull request was merged and there is no open PR that still depends on it. Squash-merged branches may not appear in git branch --merged; check the PR itself and compare the branch changes with the target branch.

    git switch main
    git pull --ff-only origin main
    git fetch origin
    .\scripts\git\afcon360-git-archive.ps1 -Action ArchiveBranch -BranchName "fix/example-completed-work"

The helper:
1. Refuses main, the permanent User branch and the permanent Driver branch.
2. Archives both local and remote tips if they differ; if they match, one archive tag preserves that commit.
3. Pushes the archive tag or tags to GitHub and verifies they exist there.
4. Only then asks you to type DELETE before deleting the original local and remote branch refs.

If you cancel at the prompt, the original branch remains and the archive tag is still available. Archive tags are under archive/branches/...; they do not clutter the active branch list.

## Archive an obsolete stash

Inspect a stash before archiving it:

    git stash show --stat --include-untracked 'stash@{2}'
    git stash show --name-status --include-untracked 'stash@{2}'

Only archive it after confirming every useful change is merged, superseded or separately preserved.

    .\scripts\git\afcon360-git-archive.ps1 -Action ArchiveStash -StashSelector 'stash@{2}'

The helper pushes an annotated tag under archive/stashes/... and verifies that GitHub has it. The tag points to the complete stash commit; its parent links retain the index and untracked-file snapshots as well. It then asks you to type DROP before removing that entry from the active local stash list.

## Restore an archived branch

Use the exact tag printed when archiving:

    .\scripts\git\afcon360-git-archive.ps1 -Action RestoreBranch -ArchiveRef "archive/branches/20261114-120000/fix-example-completed-work" -BranchName "fix/example-completed-work"

The helper refuses to overwrite an existing local or remote branch. The restored branch is recreated locally and pushed to origin.

## Resurface an archived stash

    .\scripts\git\afcon360-git-archive.ps1 -Action RestoreStash -ArchiveRef "archive/stashes/20261114-120000/example-stash-subject"
    git stash list --date=local

This puts the archived stash commit back into the active stash list; it does NOT apply its contents. Inspect it, then use git stash apply 'stash@{0}' (or the selector shown in the list) when ready. Apply preserves the stash entry; use pop only when you intentionally want to remove it after successful restoration.

## Important safeguards

- main, feat/native-user-app-integration-20261108 and feat/native-driver-app-integration-20261108 are protected.
- The helper never chooses branches or stashes for you. It does not guess that a branch is merged or a stash is obsolete.
- Archiving requires a successful push and remote verification before the original ref can be deleted.
- Branch archives are tags, not branches. Stash archives are tags whose target commit retains the complete stash parent graph, including untracked files.
- Keep a separate off-device backup for important work. A GitHub tag preserves Git objects, not external secrets, untracked files that were never stashed, or uncommitted working-tree edits.
- Do not archive while the working tree contains changes you have not committed or stashed.
