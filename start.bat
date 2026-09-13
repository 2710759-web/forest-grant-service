@echo off
chcp 65001 >nul
call "D:\ЯНАО_лесотаксация\PO\workspace\venv\Scripts\activate.bat"
cd /d "D:\GRANT Internet-service"
python -m streamlit run app.py
pause