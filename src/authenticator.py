# -*- coding: utf-8 -*-
"""
authenticator.py —— 校园网 Web 门户认证模块
==============================================
使用 Selenium 驱动本机 Microsoft Edge 浏览器，自动完成江西应用科技学院
校园网认证门户（http://172.16.20.18/）的登录操作。

设计思路
--------
校园网认证门户是一个网页。用户在页面上填写「用户名 / 密码 / 接入选项」后点击
「连接(Login)」，真正的密码加密、会话校验等逻辑由页面自身的 JavaScript 完成。
因此，与其在脚本里逆向这些加密逻辑（脆弱且可能随门户升级失效），不如直接驱动
真实浏览器，把账号密码填入对应输入框、选中「校园网学生接入」、点击登录，让
门户自己的前端代码完成剩余工作。这样脚本对门户改版的鲁棒性更强。

注意事项
--------
- 首次登录系统会强制修改密码，脚本无法代为完成；请先手动登录一次并修改密码。
- 若门户页面结构变化导致元素定位失败，可扩展文件底部 *_SELECTORS 常量中的
  候选选择器来适配。
"""
import os
import time
from enum import Enum

from config import get_base_dir

from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import (NoSuchElementException, WebDriverException,
                                         TimeoutException, StaleElementReferenceException)


class AuthResult(Enum):
    SUBMITTED = "submitted"
    RETRY = "retry"
    MANUAL = "manual"

# ---------------------------------------------------------------------------
# 候选选择器：按优先级依次尝试，命中任意一个即可，以兼容门户可能的改版。
# ---------------------------------------------------------------------------
USERNAME_SELECTORS = [
    (By.ID, "username"),
    (By.ID, "user_name"),
    (By.ID, "user"),
    (By.ID, "userid"),
    (By.ID, "account"),
    (By.NAME, "username"),
    (By.NAME, "user"),
    (By.NAME, "userid"),
    (By.CSS_SELECTOR, "input[autocomplete='username']"),
    (By.CSS_SELECTOR, "input[type='text']"),
]

PASSWORD_SELECTORS = [
    (By.ID, "password"),
    (By.ID, "pass"),
    (By.ID, "pwd"),
    (By.NAME, "password"),
    (By.NAME, "pass"),
    (By.CSS_SELECTOR, "input[type='password']"),
]

DOMAIN_SELECTORS = [
    (By.ID, "domain"),
    (By.NAME, "domain"),
    (By.ID, "domain_select"),
    (By.CSS_SELECTOR, "select[name*='domain']"),
    (By.CSS_SELECTOR, "select"),
]

LOGIN_BUTTON_SELECTORS = [
    (By.ID, "login"),
    (By.ID, "login_button"),
    (By.ID, "login-btn"),
    (By.NAME, "login"),
    (By.CSS_SELECTOR, "input[type='submit']"),
    (By.CSS_SELECTOR, "button[type='submit']"),
    (By.CSS_SELECTOR, "a.login"),
    (By.CSS_SELECTOR, ".login-btn"),
]


def _find_first(driver, selectors, timeout):
    """在给定时间内依次尝试候选选择器，返回第一个可见且可用的元素。"""
    def find_visible(_):
        for by, value in selectors:
            for el in driver.find_elements(by, value):
                if el.is_displayed() and el.is_enabled():
                    return el
        return False
    try:
        return WebDriverWait(driver, timeout, poll_frequency=0.3,
                             ignored_exceptions=(NoSuchElementException,
                                                 StaleElementReferenceException)).until(find_visible)
    except TimeoutException:
        return None


def _select_access_option(select_el, wanted):
    """从「接入选项」下拉框中选中目标选项（如“校园网学生接入”）。"""
    sel = Select(select_el)
    for opt in sel.options:
        text = (opt.text or "").strip()
        if text == wanted:
            sel.select_by_visible_text(opt.text)
            return text
        if opt.get_attribute("value") == wanted:
            sel.select_by_value(wanted)
            return text
    raise ValueError("门户中没有配置的接入选项，请检查 account.access_option。")


def _build_driver(cfg):
    """构建并返回 Edge WebDriver。"""
    browser = cfg.get("browser", {})
    options = EdgeOptions()
    if browser.get("headless"):
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--log-level=3")  # 降低驱动日志噪音
    options.add_experimental_option("excludeSwitches", ["enable-logging"])

    driver_path = browser.get("driver_path", "")
    if driver_path:
        if not os.path.isabs(driver_path):
            driver_path = os.path.join(get_base_dir(), driver_path)
        if not os.path.isfile(driver_path):
            raise FileNotFoundError("指定的 Edge 驱动文件不存在，请检查 browser.driver_path。")
        # 用户显式指定了 msedgedriver 路径
        service = EdgeService(executable_path=driver_path)
        return webdriver.Edge(service=service, options=options)
    # 未指定路径时，由 Selenium Manager 自动下载/匹配 msedgedriver
    return webdriver.Edge(options=options)


def prepare_driver(cfg, logger):
    """联网时预先准备并验证驱动；不访问门户、不提交账号密码。"""
    driver = None
    try:
        preparation_cfg = dict(cfg)
        preparation_cfg["browser"] = dict(cfg["browser"], headless=True)
        logger.info("正在准备并验证 Edge 驱动，请保持联网…")
        driver = _build_driver(preparation_cfg)
        logger.info("Edge 驱动已准备好。Edge 升级后可再次运行 --prepare-driver。")
        return True
    except Exception as e:
        logger.error("驱动准备失败：%s。请联网重试，或设置 browser.driver_path。", e)
        return False
    finally:
        if driver is not None:
            try:
                driver.quit()
            except WebDriverException:
                pass


def _requires_manual_action(page_text):
    text = page_text.lower()
    markers = ("密码错误", "账号或密码错误", "用户名或密码错误", "账户或密码错误",
               "账号不存在", "用户不存在", "请修改密码", "必须修改密码",
               "incorrect password", "invalid username or password", "change your password")
    return any(marker in text for marker in markers) or ("首次" in text and "修改密码" in text)


def authenticate(cfg, logger):
    """提交认证，区分可重试故障和需要人工处理的门户提示。

    SUBMITTED 仅代表已提交；外网连通性由主流程进一步确认。
    """
    network_cfg = cfg.get("network", {})
    account = cfg.get("account", {})
    browser_cfg = cfg.get("browser", {})
    portal_url = network_cfg.get("portal_url", "http://172.16.20.18/")
    timeout = browser_cfg.get("timeout", 30)

    username = account.get("username", "").strip()
    password = account.get("password", "")
    access_option = account.get("access_option", "校园网学生接入")

    if not username or not password:
        logger.error("账号或密码为空，请先编辑 config/config.json 或运行 --setup。")
        return AuthResult.MANUAL

    driver = None
    try:
        logger.info("正在启动 Microsoft Edge 浏览器…")
        driver = _build_driver(cfg)
        driver.set_page_load_timeout(timeout)
        driver.get(portal_url)
        logger.info("已打开认证门户：%s", portal_url)

        # 1) 用户名
        user_el = _find_first(driver, USERNAME_SELECTORS, timeout)
        if user_el is None:
            raise RuntimeError("未找到用户名输入框，门户页面可能已改版，请反馈或手动登录。")
        user_el.clear()
        user_el.send_keys(username)

        # 2) 密码
        pwd_el = _find_first(driver, PASSWORD_SELECTORS, timeout)
        if pwd_el is None:
            raise RuntimeError("未找到密码输入框，门户页面可能已改版。")
        pwd_el.clear()
        pwd_el.send_keys(password)

        # 3) 接入选项（下拉框，若存在）
        domain_el = _find_first(driver, DOMAIN_SELECTORS, min(timeout, 5))
        if domain_el is not None:
            if domain_el.tag_name.lower() != "select":
                raise ValueError("接入选项控件不受支持，请手动登录或更新门户适配。")
            chosen = _select_access_option(domain_el, access_option)
            if chosen:
                logger.info("已选择接入选项：%s", chosen)

        # 4) 点击登录/连接按钮
        btn = _find_first(driver, LOGIN_BUTTON_SELECTORS, timeout)
        if btn is None:
            raise RuntimeError("未找到登录按钮，门户页面可能已改版。")
        btn.click()
        logger.info("已提交登录请求，等待门户处理…")

        # 5) 等待门户完成跳转/处理
        time.sleep(3)

        # 6) 首次登录改密提示检测（尽力而为）
        try:
            page_text = driver.find_element(By.TAG_NAME, "body").text
        except Exception:
            page_text = ""
        if _requires_manual_action(page_text):
            logger.warning("门户提示账号、密码或首次改密需要人工处理，请手动登录检查后重启工具。")
            return AuthResult.MANUAL

        return AuthResult.SUBMITTED
    except (ValueError, FileNotFoundError) as e:
        logger.error("认证配置需要修正：%s", e)
        return AuthResult.MANUAL
    except WebDriverException as e:
        logger.error("Edge 驱动异常：%s", e)
        return AuthResult.RETRY
    except Exception as e:
        logger.error("认证过程发生异常：%s", e)
        return AuthResult.RETRY
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
