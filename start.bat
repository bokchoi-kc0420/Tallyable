@echo off
rem Double-click to open Tallyable with the free stand-in reader (no API cost).
cd /d "%~dp0"
git pull
python -m pip install -q -r requirements.txt
set TALLYABLE_EXTRACTOR=stub
python -m streamlit run app.py
pause
