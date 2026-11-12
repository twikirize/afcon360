<#
AFCON360 User Preview - laptop API launcher

Run this script from any PowerShell working directory. Keep the script in the
AFCON360 repository root (next to app.py and .venv), or pass -RepoRoot.

Safety properties:
- Always selects APP_ENV=testing and FLASK_ENV=testing.
- Refuses to start unless the effective and connected database is exactly
  afcon360_test and PostgreSQL reports UTC.
- Checks the local Redis-compatible service before starting Flask.
- Binds Flask to 0.0.0.0 so a phone on the same LAN/hotspot can reach it.
- Opens TCP/5000 only to LocalSubnet, never to arbitrary Internet addresses.
- Does not migrate, seed, reset, or write to the database.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = $PSScriptRoot,
    [int]$Port = 5000,
    [switch]$SkipFirewall
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Write-Section([string]$Title) {
    Write-Host "`n========== $Title ==========" -ForegroundColor Cyan
}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

try {
    $RepoRoot = [System.IO.Path]::GetFullPath($RepoRoot)
    if (-not (Test-Path (Join-Path $RepoRoot 'app.py'))) {
        throw "Cannot find app.py under '$RepoRoot'. Keep this script in the repository root or pass -RepoRoot."
    }

    $Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path $Python)) {
        throw "AFCON360 virtual environment not found at '$Python'. Activate/create the repository .venv first."
    }

    Set-Location $RepoRoot

    Write-Section 'AFCON360 PREVIEW SAFETY CONFIGURATION'
    $env:APP_ENV = 'testing'
    $env:FLASK_ENV = 'testing'
    $env:REDIS_URL = 'redis://127.0.0.1:6379/0'
    Write-Host "Repository : $RepoRoot"
    Write-Host 'APP_ENV    : testing'
    Write-Host 'FLASK_ENV  : testing'
    Write-Host 'Redis URL  : redis://127.0.0.1:6379/0'

    Write-Section 'POSTGRESQL CHECK'
    $pg = Test-NetConnection -ComputerName 127.0.0.1 -Port 5432 -WarningAction SilentlyContinue
    if (-not $pg.TcpTestSucceeded) {
        throw 'PostgreSQL is not listening on 127.0.0.1:5432. Start PostgreSQL 18 and run this script again.'
    }
    Write-Host 'PostgreSQL TCP 5432: reachable' -ForegroundColor Green

    Write-Section 'REDIS / MEMURAI CHECK'
    $redis = Test-NetConnection -ComputerName 127.0.0.1 -Port 6379 -WarningAction SilentlyContinue
    if (-not $redis.TcpTestSucceeded) {
        throw 'Redis/Memurai is not reachable on 127.0.0.1:6379. Start the configured Redis-compatible service and run this script again.'
    }
    Write-Host 'Redis-compatible TCP 6379: reachable' -ForegroundColor Green

    Write-Section 'DATABASE IDENTITY AND TIMEZONE GUARD'
    $pythonCheck = @'
import os
import sys
from sqlalchemy import text
from sqlalchemy.engine import make_url
from app import create_app
from app.extensions import db

app = create_app()
url = make_url(app.config["SQLALCHEMY_DATABASE_URI"])
print("APP_ENV:", os.getenv("APP_ENV"))
print("FLASK_ENV:", os.getenv("FLASK_ENV"))
print("EFFECTIVE DATABASE:", url.database)
print("FLASK TESTING:", app.config.get("TESTING"))
if url.database != "afcon360_test":
    raise SystemExit("SAFETY STOP: effective database is not afcon360_test")
if not app.config.get("TESTING"):
    raise SystemExit("SAFETY STOP: Flask TESTING configuration is not enabled")
with app.app_context():
    row = db.session.execute(text("SELECT current_database(), current_user, current_setting('TimeZone')")).one()
    print("CONNECTED DATABASE:", row[0])
    print("DATABASE ROLE:", row[1])
    print("TIMEZONE:", row[2])
    if row[0] != "afcon360_test":
        raise SystemExit("SAFETY STOP: connected database is not afcon360_test")
    if row[2] != "UTC":
        raise SystemExit("SAFETY STOP: database timezone is not UTC")
print("DATABASE SAFETY CHECK PASSED")
'@
    $pythonCheck | & $Python -
    if ($LASTEXITCODE -ne 0) {
        throw 'Database safety check failed. Flask will not be started.'
    }

    Write-Section 'REDIS PING CHECK'
    $redisCheck = @'
import os
import redis
client = redis.Redis.from_url(os.environ["REDIS_URL"], socket_connect_timeout=3, socket_timeout=3)
print("REDIS PING:", client.ping())
if not client.ping():
    raise SystemExit("Redis ping failed")
'@
    $redisCheck | & $Python -
    if ($LASTEXITCODE -ne 0) {
        throw 'Redis PING failed. Flask will not be started.'
    }

    Write-Section 'PHONE-REACHABLE LAPTOP ADDRESSES'
    $upIndexes = @(
        Get-NetAdapter -IncludeHidden -ErrorAction SilentlyContinue |
            Where-Object { $_.Status -eq 'Up' } |
            ForEach-Object { $_.ifIndex }
    )
    $addresses = @(
        Get-NetIPAddress -AddressFamily IPv4 -AddressState Preferred -ErrorAction SilentlyContinue |
            Where-Object {
                $_.InterfaceIndex -in $upIndexes -and
                $_.IPAddress -ne '127.0.0.1' -and
                $_.IPAddress -notlike '169.254.*' -and
                $_.PrefixLength -ge 1 -and $_.PrefixLength -le 30 -and
                ($_.InterfaceAlias -like 'Local Area Connection*' -or
                 $_.InterfaceAlias -match 'Wi-Fi|Wireless|Ethernet')
            } |
            ForEach-Object {
                $rank = 9
                if ($_.InterfaceAlias -like 'Local Area Connection*') { $rank = 0 }
                elseif ($_.InterfaceAlias -match 'Wi-Fi|Wireless') { $rank = 1 }
                elseif ($_.InterfaceAlias -match 'Ethernet') { $rank = 2 }
                [pscustomobject]@{
                    Rank = $rank
                    Interface = $_.InterfaceAlias
                    IP = $_.IPAddress
                    Prefix = $_.PrefixLength
                    URL = "http://$($_.IPAddress):$Port"
                }
            } | Sort-Object Rank, Interface
    )

    if ($addresses.Count -eq 0) {
        throw 'No active Wi-Fi, Windows hotspot, or Ethernet IPv4 address was found. Connect the laptop and phone to the same network, then retry.'
    }

    $addresses | Format-Table Interface, IP, Prefix, URL -AutoSize
    Write-Host 'Choose the address belonging to the network shared with your phone:' -ForegroundColor Yellow
    Write-Host ' - Phone connected to LAPTOP hotspot: use the Local Area Connection* / Wi-Fi Direct address (often 192.168.137.1).'
    Write-Host ' - Laptop connected to PHONE hotspot: use the Wi-Fi address assigned by the phone hotspot.'
    Write-Host ' - Both connected to the same router: use the Wi-Fi/Ethernet address on that shared network.'

    Write-Section 'WINDOWS FIREWALL'
    if (-not $SkipFirewall) {
        $ruleName = 'AFCON360 User Preview API TCP 5000 - LocalSubnet'
        $rule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
        if (-not $rule) {
            $firewallCommand = "New-NetFirewallRule -DisplayName '$ruleName' -Description 'AFCON360 local preview API; TCP 5000 restricted to directly connected LocalSubnet clients.' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -RemoteAddress LocalSubnet -Profile Any -ErrorAction Stop | Out-Null"
            if (Test-IsAdministrator) {
                New-NetFirewallRule -DisplayName $ruleName -Description 'AFCON360 local preview API; TCP 5000 restricted to directly connected LocalSubnet clients.' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -RemoteAddress LocalSubnet -Profile Any | Out-Null
                Write-Host 'Created firewall rule: Profile Any, RemoteAddress LocalSubnet, TCP 5000.' -ForegroundColor Green
            } else {
                $answer = Read-Host 'A one-time firewall rule is needed for laptop/phone networks. Allow a small Administrator prompt to create a rule limited to LocalSubnet and TCP 5000? [Y/n]'
                if ([string]::IsNullOrWhiteSpace($answer) -or $answer -match '^(y|yes)$') {
                    try {
                        $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($firewallCommand))
                        $arguments = "-NoProfile -ExecutionPolicy Bypass -EncodedCommand $encoded"
                        $elevated = Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') -Verb RunAs -ArgumentList $arguments -Wait -PassThru
                        if ($elevated.ExitCode -ne 0) { throw "Administrator firewall setup exited with code $($elevated.ExitCode)." }
                        $rule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
                        if (-not $rule) { throw 'Firewall rule was not found after the Administrator setup.' }
                        Write-Host 'Created the scoped firewall rule. Flask will still run in this normal PowerShell window.' -ForegroundColor Green
                    } catch {
                        Write-Warning "Could not create the scoped firewall rule: $($_.Exception.Message)"
                        Write-Warning 'The API can start, but Windows Firewall may block the phone until the rule is installed.'
                    }
                } else {
                    Write-Warning 'Firewall setup was declined. The API will start, but Windows Firewall may block the phone.'
                }
            }
        } else {
            Write-Host "Firewall rule exists: $ruleName"
            Write-Host 'Check that it is enabled and has Profile Any / RemoteAddress LocalSubnet if the phone cannot connect.'
        }
    } else {
        Write-Host 'Firewall configuration skipped by request.'
    }

    Write-Section 'PORT 5000 CHECK'
    $existing = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    if ($existing.Count -gt 0) {
        $owners = $existing | Select-Object -ExpandProperty OwningProcess -Unique
        throw "Port $Port is already occupied by PID(s): $($owners -join ', '). Stop the old API process after confirming what it is; this script will not terminate another process automatically."
    }

    Write-Section 'STARTING FLASK - TEST DATABASE ONLY'
    Write-Host "Phone API URL(s):"
    $addresses | ForEach-Object { Write-Host "  $($_.URL)" -ForegroundColor Green }
    Write-Host "Health path: /api/health/ping"
    Write-Host 'Keep this PowerShell window open. Press Ctrl+C to stop Flask.' -ForegroundColor Yellow
    Write-Host 'Production database selection is explicitly blocked by the safety guard.' -ForegroundColor Green

    & $Python -m flask --app 'app:create_app()' run --host 0.0.0.0 --port $Port --no-reload
    if ($LASTEXITCODE -ne 0) {
        throw "Flask exited with code $LASTEXITCODE. Review the server output above."
    }
}
catch {
    Write-Host "`nAFCON360 PREVIEW STARTUP STOPPED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
