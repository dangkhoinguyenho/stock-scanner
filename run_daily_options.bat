@echo off
REM Runs the daily options snapshot job (jobs/daily_options_snapshot.py) and
REM appends everything it prints to logs/daily_options.log. This file is what
REM Windows Task Scheduler actually launches once a day — see README.md's
REM "Running the daily options job" section for the one-time setup command.

REM %~dp0 = the folder this .bat file itself lives in, with a trailing
REM backslash. Using it (instead of assuming a working directory) means this
REM script works correctly no matter what folder Task Scheduler starts it
REM from — a common gotcha with scheduled scripts.
cd /d "%~dp0"

if not exist logs mkdir logs

".venv\Scripts\python.exe" -m stock_scanner.jobs.daily_options_snapshot >> logs\daily_options.log 2>&1
