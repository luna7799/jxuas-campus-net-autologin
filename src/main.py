# -*- coding: utf-8 -*-
"""
main.py —— 主程序入口
======================
负责解析命令行参数、加载配置、执行交互式初始化，以及启动常驻的「检测-认证」循环。

命令行用法
----------
    python src/main.py                      # 常驻模式：循环检测并自动认证
    python src/main.py --once               # 只执行一次检测+认证，然后退出
    python src/main.py --setup              # 交互式初始化（填写账号密码等）
    python src/main.py --headless           # 常驻模式 + Edge 无头运行
    python src/main.py --install-autostart  # 注册开机自启动
    python src/main.py --uninstall-autostart# 取消开机自启动
"""
import argparse
import sys
import time

import config as config_mod
from logger import setup_logger
import network
import authenticator
import autostart


def parse_args():
    parser = argparse.ArgumentParser(
        prog="jxuas-autologin",
        description="江西应用科技学院校园网(JXUAS)自动连接与认证工具",
    )
    parser.add_argument("--once", action="store_true",
                        help="仅执行一次检测与认证后退出")
    parser.add_argument("--setup", action="store_true",
                        help="交互式填写配置(账号/密码/网络名等)")
    parser.add_argument("--config", default=None,
                        help="指定配置文件路径(默认 config/config.json)")
    parser.add_argument("--headless", action="store_true",
                        help="Edge 无头模式(后台运行，不弹出浏览器窗口)")
    parser.add_argument("--install-autostart", action="store_true",
                        help="注册开机自启动")
    parser.add_argument("--uninstall-autostart", action="store_true",
                        help="取消开机自启动")
    return parser.parse_args()


def run_setup(path):
    """交互式填写并保存配置。"""
    print("=" * 50)
    print("  JXUAS 校园网自动连接 - 配置初始化")
    print("=" * 50)
    cfg = config_mod.load_config(path)

    username = input("请输入学号(用户名)：").strip()
    password = input("请输入密码：").strip()
    ssid = input("请输入校园网 WiFi 名称(默认 %s)：" % cfg["network"]["ssid"]).strip()
    access = input("请输入接入选项(默认 %s)：" % cfg["account"]["access_option"]).strip()

    if username:
        cfg["account"]["username"] = username
    if password:
        cfg["account"]["password"] = password
    if ssid:
        cfg["network"]["ssid"] = ssid
    if access:
        cfg["account"]["access_option"] = access

    config_mod.save_config(path, cfg)
    print("配置已保存到：%s" % (path or config_mod.get_config_path()))
    print("后续可直接运行程序，如需修改请编辑该文件。")


def once(cfg, logger):
    """执行一次「检测 + 自动连接 + 认证」流程。"""
    net = cfg["network"]

    if network.is_authenticated(net["test_url"]):
        logger.info("当前已联网且已认证，无需操作。")
        return

    logger.info("检测到网络未认证，开始自动连接…")
    if net.get("ssid"):
        network.connect_wifi(net["ssid"], net.get("ssid_backup"))
        time.sleep(2)

    if network.is_authenticated(net["test_url"]):
        logger.info("连接后已自动认证成功。")
        return

    if not network.can_reach_portal(net["portal_url"]):
        logger.warning("无法访问认证门户，可能当前不在校园网环境，跳过认证。")
        return

    max_retry = cfg["auto_login"]["max_retry"]
    for i in range(1, max_retry + 1):
        logger.info("第 %d/%d 次尝试调用 Edge 完成认证…", i, max_retry)
        try:
            authenticator.authenticate(cfg, logger)
        except Exception as e:
            logger.error("认证异常：%s", e)
        time.sleep(2)
        if network.is_authenticated(net["test_url"]):
            logger.info("认证成功，已接入校园网。")
            return

    logger.warning("多次尝试仍未认证成功，请检查账号密码或手动登录。")


def run_loop(cfg, logger):
    """常驻循环：周期性检测，需要时自动认证。"""
    interval = cfg["auto_login"]["check_interval"]
    logger.info("进入常驻模式（检测间隔 %d 秒），按 Ctrl+C 退出。", interval)
    while True:
        try:
            once(cfg, logger)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            logger.error("主循环异常：%s", e)
        time.sleep(interval)


def main():
    args = parse_args()

    # 开机自启动相关操作不依赖配置，优先处理
    if args.install_autostart:
        print("已注册开机自启动。" if autostart.install() else "注册开机自启动失败。")
        return 0
    if args.uninstall_autostart:
        print("已取消开机自启动。" if autostart.uninstall() else "取消失败(可能本就没有注册)。")
        return 0

    config_path = args.config or config_mod.get_config_path()

    if args.setup:
        run_setup(config_path)
        return 0

    cfg = config_mod.load_config(config_path)
    if args.headless:
        cfg["browser"]["headless"] = True

    logger = setup_logger(cfg["logging"])

    if args.once:
        once(cfg, logger)
        return 0

    run_loop(cfg, logger)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n已退出。")
        sys.exit(0)
