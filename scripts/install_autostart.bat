@echo off
chcp 65001 >nul
title JXUAS 校园网自动连接 - 安装开机自启动
cd /d "%~dp0.."

echo.
echo ==========================================
echo   安装开机自启动（JXUAS_AutoLogin）
echo ==========================================
echo.

if exist "dist\jxuas-autologin.exe" (
    echo 检测到已打包程序 dist\jxuas-autologin.exe，正在注册...
    "dist\jxuas-autologin.exe" --install-autostart
) else (
    echo 未检测到打包程序，改用 Python 源码注册...
    python "src\main.py" --install-autostart
)

echo.
echo 完成。按任意键退出...
pause >nul
