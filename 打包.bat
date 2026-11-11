@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "APP_NAME=轻待办"

echo ============================================
echo   打包 %APP_NAME% 便携版 exe
echo ============================================
echo.

rem ---- 找一个带 PySide6 + qfluentwidgets 的 Python ----
set "PYCMD="
py -3.15 -c "import PySide6, qfluentwidgets, PIL" >nul 2>&1 && set "PYCMD=py -3.15"
if not defined PYCMD (
    python -c "import PySide6, qfluentwidgets, PIL" >nul 2>&1 && set "PYCMD=python"
)
if not defined PYCMD (
    echo [错误] 没有找到带 PySide6 / qfluentwidgets / pillow 的 Python。
    echo        请先安装依赖：
    echo        pip install PySide6-Fluent-Widgets pillow pyinstaller
    pause
    exit /b 1
)
echo 使用解释器：%PYCMD%
echo.

echo [1/3] 生成图标 ...
%PYCMD% -m app.icon assets\icon.ico
if errorlevel 1 goto :fail

echo [2/3] 清理旧构建 ...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [3/3] 打包单文件 exe ...
%PYCMD% -m PyInstaller --noconfirm --clean 轻待办.spec
if errorlevel 1 goto :fail

echo.
echo ============================================
echo   完成：dist\%APP_NAME%.exe
echo   把这个 exe 放到任意文件夹即可使用，
echo   首次运行会在 exe 旁边生成 data 目录（数据库）。
echo ============================================
pause
exit /b 0

:fail
echo.
echo 打包失败，请检查上面的错误信息。
pause
exit /b 1
