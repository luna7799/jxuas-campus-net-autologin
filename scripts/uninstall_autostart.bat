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
    if exist ".venv\Scripts\python.exe" (
        ".venv\Scripts\python.exe" "src\main.py" --uninstall-autostart
    ) else (
        python "src\main.py" --uninstall-autostart
    )
)
set "RUN_RESULT=%errorlevel%"

echo.
echo 完成。按任意键退出...
pause >nul
exit /b %RUN_RESULT%
