@echo off
title AFCON360 Dev Stack
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-all.ps1" -Restart %*
