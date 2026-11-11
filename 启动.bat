@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PYW="
pyw -3.15 -c "import PySide6, qfluentwidgets" >nul 2>&1 && set "PYW=pyw -3.15"
if not defined PYW (
    python -c "import PySide6, qfluentwidgets" >nul 2>&1 && set "PYW=pythonw"
)
if not defined PYW (
    echo 没有找到可用的 Python 环境，请直接运行 轻待办.exe
    pause
    exit /b 1
)

start "" %PYW% "轻待办.pyw"
exit /b 0
