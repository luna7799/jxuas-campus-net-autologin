# -*- coding: utf-8 -*-
"""
autostart.py —— 开机自启动模块（Windows）
==========================================
通过写入当前用户注册表的 Run 项实现开机自启动，无需管理员权限。
- install():   注册开机自启动
- uninstall(): 取消开机自启动
- status():    查询当前自启动状态
"""
import os
import sys
import winreg

# 注册表位置：当前用户的开机启动项
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
# 自启动项名称（唯一标识本工具）
APP_NAME = "JXUAS_AutoLogin"


def _target_command():
    """
    返回开机时需要执行的命令行：
    - 打包为 exe 时：直接指向 exe 本体；
    - 源码运行时：指向 python 解释器 + main.py 脚本。
    """
    if getattr(sys, "frozen", False):
        return '"%s"' % sys.executable
    python = sys.executable
    script = os.path.abspath(os.path.join(os.path.dirname(__file__), "main.py"))
    return '"%s" "%s"' % (python, script)


def install():
    """注册开机自启动，返回是否成功。"""
    try:
        command = _target_command()
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)
        return True
    except OSError:
        return False


def uninstall():
    """取消开机自启动，返回是否成功。"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY,
                            0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, APP_NAME)
        return True
    except FileNotFoundError:
        # 本来就没有注册，视为成功
        return True
    except OSError:
        return False


def status():
    """查询自启动状态，返回 (是否已注册, 注册的命令行)。"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return True, value
    except FileNotFoundError:
        return False, None
    except OSError:
        return False, None
