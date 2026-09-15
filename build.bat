@echo off
chcp 65001 >nul
title JXUAS 校园网自动连接 - 一键打包脚本
setlocal
cd /d "%~dp0"

echo ==========================================
echo   JXUAS 校园网自动连接 - 一键打包
echo ==========================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.8+ 并勾选 "Add to PATH"。
    pause
    exit /b 1
)

echo [1/4] 创建虚拟环境 .venv ...
python -m venv .venv
call ".venv\Scripts\activate.bat"

echo [2/4] 安装依赖（selenium / requests / pyinstaller）...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt pyinstaller

echo [3/4] 打包为单文件 exe ...
pyinstaller --noconfirm --clean --onefile --name jxuas-autologin --console src\main.py

echo [4/4] 复制配置文件到输出目录 ...
if not exist "dist\config" mkdir "dist\config"
copy /y "config\config.json" "dist\config\config.json" >nul
copy /y "config\config.example.json" "dist\config\config.example.json" >nul

echo.
echo 打包完成！
echo   输出文件：dist\jxuas-autologin.exe
echo   配置文件：dist\config\config.json
echo.
pause
endlocal
