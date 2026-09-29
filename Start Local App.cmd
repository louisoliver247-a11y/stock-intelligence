@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\local.ps1" start
if errorlevel 1 (pause) else (start "" http://localhost:8080)
