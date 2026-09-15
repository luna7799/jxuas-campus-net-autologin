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

from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoSuchElementException, WebDriverException

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
    (By.CSS_SELECTOR, "input[type='text']"),
    (By.CSS_SELECTOR, "input[autocomplete='username']"),
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
    end = time.time() + timeout
    while time.time() < end:
        for by, value in selectors:
            try:
                el = driver.find_element(by, value)
                if el.is_displayed() and el.is_enabled():
                    return el
            except NoSuchElementException:
                continue
        time.sleep(0.3)
    return None


def _select_access_option(select_el, wanted):
    """从「接入选项」下拉框中选中目标选项（如“校园网学生接入”）。"""
    try:
        sel = Select(select_el)
        # 1) 精确匹配可见文本
        for opt in sel.options:
            text = (opt.text or "").strip()
            if text == wanted:
                sel.select_by_visible_text(text)
                return text
        # 2) 模糊匹配：包含“学生”或“校园网”关键字
        for opt in sel.options:
            text = (opt.text or "").strip()
            if "学生" in text or "校园网" in text:
                sel.select_by_visible_text(text)
                return text
        # 3) 兜底：保持默认选中项，不报错
        return None
    except Exception:
        return None


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
    if driver_path and os.path.exists(driver_path):
        # 用户显式指定了 msedgedriver 路径
        service = EdgeService(executable_path=driver_path)
        return webdriver.Edge(service=service, options=options)
    # 未指定路径时，由 Selenium Manager 自动下载/匹配 msedgedriver
    return webdriver.Edge(options=options)


def authenticate(cfg, logger):
    """执行一次完整的门户认证。成功返回 True，失败返回 False。"""
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
        return False

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
        if domain_el is not None and domain_el.tag_name == "select":
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
        lowered = page_text.lower()
        if "修改密码" in page_text or "change password" in lowered:
            logger.warning("检测到首次登录需修改密码，请先手动完成一次改密，之后即可自动认证。")

        return True
    except WebDriverException as e:
        logger.error("Edge 驱动异常：%s", e)
        return False
    except Exception as e:
        logger.error("认证过程发生异常：%s", e)
        return False
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
