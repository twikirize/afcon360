<#
.SYNOPSIS
    Stops the AFCON360 development stack started by start-all.
.DESCRIPTION
    Kills the start-all-launched Metro listener, Metro manager, Metro/Expo
    node processes, start-all launcher, and Flask API, then frees the dev
    ports. Exclude the current Python PID when a PyCharm-owned Flask run
    evicts the start-all stack without killing itself.

    Use -DryRun to list matches without stopping anything.
#>
[CmdletBinding()]
param(
    [int]$ExcludePid = 0,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$patterns = @(
    'metro_manager\.py',
    'metro_listener\.py',
    'start-user-metro\.ps1',
    'start-all\.ps1',
    'start-all\.bat',
    'app\.py',
    'expo[\\/].*start',
    '@expo[\\/]cli'
)
$regex = ($patterns | ForEach-Object { "($_)" }) -join '|'
$processes = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'powershell.exe' OR Name = 'cmd.exe' OR Name = 'node.exe' OR Name = 'npx.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.ProcessId -ne $ExcludePid -and $_.CommandLine -and $_.CommandLine -match $regex } |
    Sort-Object ProcessId -Unique

foreach ($proc in $processes) {
    if ($DryRun) {
        Write-Host ("Would stop PID {0}: {1}" -f $proc.ProcessId, $proc.CommandLine)
    } else {
        Write-Host ("Stopping PID {0}..." -f $proc.ProcessId)
        & taskkill.exe /PID $proc.ProcessId /T /F 2>$null | Out-Null
    }
}

$ports = @(8081, 8082, 5000)
foreach ($port in $ports) {
    $owners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($ownerPid in $owners) {
        if ($ownerPid -eq $ExcludePid) { continue }
        if ($DryRun) {
            Write-Host ("Would free port {0} (PID {1})" -f $port, $ownerPid)
        } else {
            Write-Host ("Freeing port {0} (PID {1})..." -f $port, $ownerPid)
            & taskkill.exe /PID $ownerPid /T /F 2>$null | Out-Null
        }
    }
}

if ($DryRun) {
    Write-Host "Dry run only; nothing was stopped."
    exit 0
}

for ($i = 0; $i -lt 20; $i++) {
    $busy = @(8081, 8082, 5000) | Where-Object {
        Get-NetTCPConnection -LocalPort $_ -State Listen -ErrorAction SilentlyContinue
    }
    if (-not $busy) { break }
    Start-Sleep -Milliseconds 250
}
Write-Host "AFCON360 dev stack stopped."
