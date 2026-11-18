@echo off
REM Double-click friendly wrapper around scripts\setup_windows.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_windows.ps1" %*
