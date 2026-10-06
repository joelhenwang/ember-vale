@echo off
rem Double-click to start Ember Vale. The first start downloads the launcher.
rem "Start Ember Vale.cmd update" fetches the newest launcher again.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher\start.ps1" %*
if errorlevel 1 pause
