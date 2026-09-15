# -*- coding: utf-8 -*-
"""
config.py —— 配置加载与保存模块
=================================
- 提供默认配置 DEFAULT_CONFIG；
- 首次运行时自动在 config/ 目录下生成 config.json；
- 加载时把用户配置与默认配置做「深合并」，保证后续新增字段也能生效。

配置文件采用 JSON 格式、UTF-8 编码，可直接用文本编辑器修改。
"""
import copy
import json
import os
import sys


# 默认配置：即 config/config.json 的「模板」。新增字段只需在此补充，
# 旧配置文件合并后仍能取到默认值，无需用户手动迁移。
DEFAULT_CONFIG = {
    "network": {
        # 校园无线信号：通用信号 JXUAS；宿舍信号偏弱时可切换 JXUAS-2.4G
        "ssid": "JXUAS",
        "ssid_backup": "JXUAS-2.4G",
        # 认证门户 / 自助服务平台地址（来自校方公众号教程）
        "portal_url": "http://172.16.20.18/",
        "self_service_url": "http://172.16.20.19:8080/selfservice/",
        # 用于判断是否已联网的测试地址
        "test_url": "https://www.baidu.com/",
    },
    "account": {
        # 用户名：学号；初始密码为身份证后 6 位（首次登录需改密）
        "username": "",
        "password": "",
        # 接入选项：校园网学生接入
        "access_option": "校园网学生接入",
        # 运营商宽带绑定预留字段（绑定需在自助平台手动完成一次）
        "broadband_account": "",
        "broadband_password": "",
    },
    "browser": {
        # 手动指定 msedgedriver 路径；留空则交由 Selenium Manager 自动下载/匹配
        "driver_path": "",
        # 无头模式：True 则不显示浏览器窗口
        "headless": False,
        # 页面加载 / 元素定位超时（秒）
        "timeout": 30,
    },
    "auto_login": {
        # 常驻模式下每轮检测的间隔（秒）
        "check_interval": 30,
        # 认证失败后的最大重试次数
        "max_retry": 3,
    },
    "logging": {
        # 日志级别：DEBUG / INFO / WARNING / ERROR
        "level": "INFO",
        # 日志目录（相对程序基目录）
        "log_dir": "logs",
    },
}


def get_base_dir():
    """
    返回程序基目录：
    - 打包为 exe 时：exe 所在目录（配置文件也放在旁边的 config/ 下）；
    - 源码运行时：仓库根目录（src/config.py 的上一级目录）。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # src/config.py -> 上一级是 src，再上一级是仓库根目录
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_config_path():
    """返回默认配置文件路径：<基目录>/config/config.json"""
    return os.path.join(get_base_dir(), "config", "config.json")


def _deep_merge(base, override):
    """把 override 递归合并进 base（就地修改 base），返回 base。"""
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def load_config(path=None):
    """
    加载配置：默认配置 + 配置文件内容做深合并。
    文件不存在时自动生成默认配置，并提示用户填写账号密码。
    """
    config_path = path or get_config_path()
    config = copy.deepcopy(DEFAULT_CONFIG)

    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            _deep_merge(config, user_cfg)
        except (json.JSONDecodeError, OSError) as e:
            print("[警告] 配置文件解析失败(%s)，使用默认配置。" % e)
    else:
        save_config(config_path, config)
        print("[提示] 已生成默认配置文件：%s，请填写账号密码。" % config_path)
    return config


def save_config(path, config):
    """把配置以 JSON 形式（缩进 2 空格、UTF-8）写入指定路径。"""
    config_path = path or get_config_path()
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
