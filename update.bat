@echo off
rem Updates AutoSaga to the newest release. Settings and data are kept.
rem Started through Python, not through the program's own launcher: the update replaces
rem that launcher, and Windows does not replace a program that is running.
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" -m efactura update %*
echo.
pause
