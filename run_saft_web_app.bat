@echo off
cd /d %~dp0
python -m pip install -r requirements_saft_web_app_gi.txt
python -m streamlit run saft_web_app_gi.py
pause
