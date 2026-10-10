@echo off
chcp 65001 >nul
title JXUAS 校园网自动连接 - 一键打包脚本
setlocal EnableExtensions
cd /d "%~dp0"

echo ==========================================
echo   JXUAS 校园网自动连接 - 一键打包
echo ==========================================
echo.

set "BUILD_PYTHON=.venv\Scripts\python.exe"
if not exist "%BUILD_PYTHON%" (
    python -m venv .venv
    if errorlevel 1 goto failed
)

echo [1/4] 安装打包依赖...
"%BUILD_PYTHON%" -m pip install -r requirements-build.txt
if errorlevel 1 goto failed

echo [2/4] 运行回归测试...
"%BUILD_PYTHON%" -m unittest discover -s tests -v
if errorlevel 1 goto failed

echo [3/4] 打包程序和 Selenium Manager...
"%BUILD_PYTHON%" -m PyInstaller --noconfirm --clean --onefile --name jxuas-autologin --console --paths src --collect-all selenium src\main.py
if errorlevel 1 goto failed

echo [4/4] 生成不含个人账号的发布配置...
"%BUILD_PYTHON%" scripts\prepare_release.py dist
if errorlevel 1 goto failed

"%BUILD_PYTHON%" scripts\check_package.py dist
if errorlevel 1 goto failed

echo.
echo 打包完成！
echo   输出文件：dist\jxuas-autologin.exe
echo   配置文件：dist\config\config.json
echo 发布配置已重置为空账号；本机 config\config.json 保持不变。
echo.
if /i not "%~1"=="--no-pause" pause
exit /b 0

:failed
echo [错误] 打包失败，已停止。请查看上方错误提示。
if /i not "%~1"=="--no-pause" pause
exit /b 1
