@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "send_news.py"
) else (
  python "send_news.py"
)
exit /b %ERRORLEVEL%
