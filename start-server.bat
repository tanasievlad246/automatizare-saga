@echo off
rem Starts AutoSaga in server mode: every computer on the office network opens it in the
rem browser at http://<this PC's address>:8765/ui/ (the port in config.toml). No login is asked.
rem Only one copy runs at a time: close start.bat's window, or run "uv run efactura stop", first.
rem Keep this window open while the others work; closing it stops the program.
cd /d "%~dp0"
uv run efactura serve --network
