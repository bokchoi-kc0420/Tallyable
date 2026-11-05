@echo off
rem Double-click to open Tallyable reading receipts with Claude (uses API credits).
cd /d "%~dp0"
git pull
python -m pip install -q -r requirements.txt
python -m streamlit run app.py
pause
