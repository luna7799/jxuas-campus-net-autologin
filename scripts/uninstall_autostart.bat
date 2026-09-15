@echo off
chcp 65001 >nul
title JXUAS 校园网自动连接 - 取消开机自启动
cd /d "%~dp0.."

echo.
echo ==========================================
echo   取消开机自启动（JXUAS_AutoLogin）
echo ==========================================
echo.

if exist "dist\jxuas-autologin.exe" (
    "dist\jxuas-autologin.exe" --uninstall-autostart
) else (
    python "src\main.py" --uninstall-autostart
)

echo.
echo 完成。按任意键退出...
pause >nul
