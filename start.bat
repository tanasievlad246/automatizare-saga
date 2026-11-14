@echo off
rem Starts e-Factura pentru SAGA and opens it in the browser (http://autosaga.localhost:8765/ui/).
rem Keep this window open while you work; closing it stops the program.
cd /d "%~dp0"
uv run efactura serve --open
