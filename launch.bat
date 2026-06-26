@echo off
cd /d "%~dp0"
python main.py
if errorlevel 1 (
    echo.
    echo 启动失败，请确认已安装 Python 3.10+ 并执行过：
    echo   pip install -r requirements.txt
    pause
)
