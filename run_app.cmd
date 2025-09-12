@echo off
setlocal
cd /d "%~dp0"
"%~dp0constru\Scripts\python.exe" -m streamlit run app.py
