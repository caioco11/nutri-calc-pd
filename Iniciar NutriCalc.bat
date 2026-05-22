@echo off
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo Iniciando NutriCalc P&D...
echo Acesse: http://localhost:8501
start "" http://localhost:8501
.venv\Scripts\streamlit.exe run app.py
pause
