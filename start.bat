@echo off
REM Windows: double-click this file to start the desk.
cd /d "%~dp0"
python start.py
if errorlevel 1 pause
