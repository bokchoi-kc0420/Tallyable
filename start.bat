@echo off
rem Double-click to open Tallyable with the free stand-in reader (no API cost).
cd /d "%~dp0"
git pull
python -m pip install -q -r requirements.txt
rem Start every launch on step 1 with an empty event (past events stay in the sidebar).
if exist output\session.json del output\session.json
set TALLYABLE_EXTRACTOR=stub
python -m streamlit run app.py
pause
