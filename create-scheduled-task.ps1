<# 
.SYNOPSIS
    Creates a Windows Scheduled Task to auto-start AFCON360 on user logon
.DESCRIPTION
    Run this ONCE as Administrator to create the scheduled task.
    After this, AFCON360 will start automatically when you log into Windows.
#>

param()

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "Must run as Administrator. Right-click PowerShell -> Run as Administrator."
    exit 1
}

$TaskName = "AFCON360 Auto-Start"
$ScriptPath = "C:\Users\OBED\Desktop\afcon360-user-dev\start-afcon360.ps1"
$BatPath = "C:\Users\OBED\Desktop\afcon360-user-dev\start-afcon360.bat"

Write-Host "Creating scheduled task: $TaskName" -ForegroundColor Cyan

# Remove existing task if exists
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# Create trigger: At logon
$trigger = New-ScheduledTaskTrigger -AtLogOn

# Create action: Run the batch file (hidden window)
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c start /min ""AFCON360"" ""$BatPath"""

# Settings
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RunOnlyIfNetworkAvailable

# Register task
Register-ScheduledTask -TaskName $TaskName -Trigger $trigger -Action $action -Settings $settings -Description "Auto-starts AFCON360 Flask API + Metro Bundler on user logon" -Force

Write-Host "Scheduled task created successfully!" -ForegroundColor Green
Write-Host "AFCON360 will now start automatically when you log into Windows." -ForegroundColor Green
Write-Host ""
Write-Host "To disable: Task Scheduler -> Task Scheduler Library -> AFCON360 Auto-Start -> Disable" -ForegroundColor Yellow