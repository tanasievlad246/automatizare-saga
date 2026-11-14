@echo off
rem Starts the local efactura API on http://127.0.0.1:8765 (the port in config.toml).
rem Keep this window open, or start it hidden from Power Automate ("Run application").
cd /d "%~dp0"
uv run efactura serve
