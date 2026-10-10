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
from enum import IntEnum
from getpass import getpass

import config as config_mod
from logger import setup_logger
import network
import authenticator
import autostart


class RunResult(IntEnum):
    SUCCESS = 0
    FAILED = 1
    CONFIG_ERROR = 2
    OUTSIDE_CAMPUS = 3
    MANUAL_ACTION = 4


def configure_console():
    """确保中文提示在英文 Windows 和重定向输出中也能正常显示。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_args():
    parser = argparse.ArgumentParser(
        prog="jxuas-autologin",
        description="江西应用科技学院校园网(JXUAS)自动连接与认证工具",
    )
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--once", action="store_true",
                        help="仅执行一次检测与认证后退出")
    actions.add_argument("--setup", action="store_true",
                        help="交互式填写配置(账号/密码/网络名等)")
    parser.add_argument("--config", default=None,
                        help="指定配置文件路径(默认 config/config.json)")
    parser.add_argument("--headless", action="store_true",
                        help="Edge 无头模式(后台运行，不弹出浏览器窗口)")
    actions.add_argument("--prepare-driver", action="store_true",
                         help="联网时提前下载并验证 Edge 驱动，不进行校园网认证")
    actions.add_argument("--install-autostart", action="store_true",
                        help="注册开机自启动")
    actions.add_argument("--uninstall-autostart", action="store_true",
                        help="取消开机自启动")
    return parser.parse_args()


def run_setup(path):
    """交互式填写并保存配置。"""
    print("=" * 50)
    print("  JXUAS 校园网自动连接 - 配置初始化")
    print("=" * 50)
    cfg = config_mod.load_config(path)

    username = input("请输入学号(用户名)：").strip()
    password = getpass("请输入密码（输入时不显示）：")
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
    print("首次使用请在联网时运行 --prepare-driver，提前准备 Edge 驱动。")


def once(cfg, logger):
    """执行一次检测与认证，返回明确的运行结果。"""
    net = cfg["network"]

    if network.is_authenticated(net["test_url"]):
        logger.info("当前已联网且已认证，无需操作。")
        return RunResult.SUCCESS

    logger.info("检测到网络未认证，开始自动连接…")
    # 有线校园网可直接访问门户时，不主动切换 WiFi。
    if not network.can_reach_portal(net["portal_url"]) and net.get("ssid"):
        if not network.connect_wifi(net["ssid"], net.get("ssid_backup"), net["connect_timeout"]):
            logger.warning("未能连接主/备用 WiFi，将继续检查有线网络及认证门户。")

    if network.is_authenticated(net["test_url"]):
        logger.info("连接后已自动认证成功。")
        return RunResult.SUCCESS

    if not network.can_reach_portal(net["portal_url"]):
        logger.warning("无法访问认证门户，可能当前不在校园网环境，跳过认证。")
        return RunResult.OUTSIDE_CAMPUS

    if not cfg["account"]["username"].strip() or not cfg["account"]["password"]:
        logger.error("账号或密码为空，请运行 --setup 后重试。")
        return RunResult.CONFIG_ERROR

    max_retry = cfg["auto_login"]["max_retry"]
    for i in range(1, max_retry + 1):
        logger.info("第 %d/%d 次尝试调用 Edge 完成认证…", i, max_retry)
        try:
            result = authenticator.authenticate(cfg, logger)
            if result == authenticator.AuthResult.MANUAL:
                return RunResult.MANUAL_ACTION
        except Exception as e:
            logger.error("认证异常：%s", e)
            result = authenticator.AuthResult.RETRY
        # 提交后等待外网恢复，避免门户处理较慢时立即重复登录。
        if result == authenticator.AuthResult.SUBMITTED:
            deadline = time.monotonic() + net["auth_timeout"]
            while True:
                if network.is_authenticated(net["test_url"]):
                    logger.info("认证成功，已接入校园网。")
                    return RunResult.SUCCESS
                if time.monotonic() >= deadline:
                    break
                time.sleep(min(1, max(0, deadline - time.monotonic())))
        if i < max_retry:
            time.sleep(cfg["auto_login"]["retry_delay"])

    logger.warning("多次尝试仍未认证成功，请检查账号密码或手动登录。")
    return RunResult.FAILED


def run_loop(cfg, logger):
    """常驻循环：周期性检测，需要时自动认证。"""
    interval = cfg["auto_login"]["check_interval"]
    logger.info("进入常驻模式（检测间隔 %d 秒），按 Ctrl+C 退出。", interval)
    delay = interval
    maximum = max(interval, cfg["auto_login"]["max_backoff"])
    while True:
        try:
            result = once(cfg, logger)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            logger.error("主循环异常：%s", e)
            result = RunResult.FAILED
        if result in (RunResult.CONFIG_ERROR, RunResult.MANUAL_ACTION):
            logger.error("已停止自动重试，请修正配置或完成手动登录后重新启动。")
            return result
        if result == RunResult.FAILED:
            delay = min(maximum, delay * 2)
            logger.warning("本轮认证失败，%d 秒后重试。", delay)
        else:
            delay = interval
        time.sleep(delay)


def _main():
    args = parse_args()

    # 开机自启动相关操作不依赖配置，优先处理
    if args.install_autostart:
        installed = autostart.install(config_mod.resolve_path(args.config), args.headless)
        print("已注册开机自启动。" if installed else "注册开机自启动失败。")
        return RunResult.SUCCESS if installed else RunResult.FAILED
    if args.uninstall_autostart:
        removed = autostart.uninstall()
        print("已取消开机自启动。" if removed else "取消开机自启动失败。")
        return RunResult.SUCCESS if removed else RunResult.FAILED

    config_path = config_mod.resolve_path(args.config)

    if args.setup:
        run_setup(config_path)
        return 0

    cfg = config_mod.load_config(config_path)
    if args.headless:
        cfg["browser"]["headless"] = True

    logger = setup_logger(cfg["logging"])

    if args.prepare_driver:
        return RunResult.SUCCESS if authenticator.prepare_driver(cfg, logger) else RunResult.FAILED

    if args.once:
        return once(cfg, logger)

    return run_loop(cfg, logger)


def main():
    try:
        return _main()
    except config_mod.ConfigError as e:
        print("[错误] %s" % e, file=sys.stderr)
        return RunResult.CONFIG_ERROR
    except OSError as e:
        print("[错误] 无法完成本机文件或启动操作：%s" % e, file=sys.stderr)
        return RunResult.FAILED


if __name__ == "__main__":
    configure_console()
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n已退出。")
        sys.exit(0)
