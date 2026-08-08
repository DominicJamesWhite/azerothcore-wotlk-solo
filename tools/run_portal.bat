@echo off
REM Alonecraft player account portal -- run on demand, Ctrl-C to stop.
REM
REM Binds to the LAN by default because LAN access is the point. Account
REM creation is unauthenticated: do NOT port-forward this. Pass extra args
REM through, e.g. `run_portal.bat --host 127.0.0.1` to keep it local-only.
python "%~dp0portal\server.py" --host 0.0.0.0 --port 8090 %*
