@echo off
title AFCON360 Auto-Start
echo Starting AFCON360 (Flask + Metro + Phone)...
powershell -ExecutionPolicy Bypass -File "%~dp0start-afcon360.ps1" -LaunchPhone
pause