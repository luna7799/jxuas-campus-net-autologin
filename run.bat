@echo off
chcp 65001 >nul
title JXUAS 校园网自动连接与认证
cd /d "%~dp0"

echo ==========================================
echo   JXUAS 校园网自动连接与认证工具
echo ==========================================
echo.

if exist "dist\jxuas-autologin.exe" (
    "dist\jxuas-autologin.exe" %*
) else (
    python "src\main.py" %*
)

echo.
echo 程序已结束，按任意键退出...
pause >nul
