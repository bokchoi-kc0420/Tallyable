@echo off
rem Double-click to open Tallyable reading receipts with Claude (uses API credits).
cd /d "%~dp0"
git pull
python -m pip install -q -r requirements.txt
rem Start every launch on step 1 with an empty event (past events stay in the sidebar).
if exist output\session.json del output\session.json
rem Open the landing page first. Its buttons go to the app at localhost:8501.
start "" /b python -m http.server 3000 --directory landing >nul 2>&1
start "" http://localhost:3000
python -m streamlit run app.py --server.headless true
pause
