"""验证发布程序可启动、配置错误退出码和 Selenium Manager 的打包完整性。"""
import argparse
import json
import locale
import os
from pathlib import Path
import subprocess
import tempfile

from PyInstaller.archive.readers import CArchiveReader


def output_text(data):
    """源码通常输出 UTF-8；冻结程序通过管道时也可能使用系统代码页。"""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode(locale.getpreferredencoding(False), errors="replace")


def check_package(output_dir):
    output = Path(output_dir).resolve()
    package = output / "jxuas-autologin.exe"
    archive = CArchiveReader(str(package))
    manager_name = next(name for name in archive.toc
                        if name.replace("\\", "/").endswith("windows/selenium-manager.exe"))
    if any(name.replace("\\", "/").endswith("config/config.json") for name in archive.toc):
        raise RuntimeError("可执行文件不应内嵌个人配置。")
    environment = dict(os.environ, PYTHONIOENCODING="utf-8")
    options = dict(capture_output=True, env=environment,
                   timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        manager = temp / "selenium-manager.exe"
        manager.write_bytes(archive.extract(manager_name))
        version = subprocess.run([str(manager), "--version"], **options)
        if version.returncode != 0:
            raise RuntimeError("打包内的 Selenium Manager 无法启动：%s" % output_text(version.stderr))
        help_result = subprocess.run([str(package), "--help"], **options)
        if help_result.returncode != 0 or b"--prepare-driver" not in help_result.stdout:
            raise RuntimeError("可执行文件启动检查失败：%s" % output_text(help_result.stderr))
        invalid = temp / "invalid.json"
        invalid.write_text('{"network": null}', encoding="utf-8")
        result = subprocess.run([str(package), "--config", str(invalid), "--once"], **options)
        if result.returncode != 2 or b"network" not in result.stderr:
            raise RuntimeError("可执行文件未正确报告配置错误。")
    cfg = json.loads((output / "config" / "config.json").read_text(encoding="utf-8"))
    if any(cfg["account"][key] for key in ("username", "password", "broadband_account", "broadband_password")):
        raise RuntimeError("发布配置必须为空账号。")
    print("发布验证通过：程序可启动，驱动管理器完整，配置错误退出码正确，发布账号为空。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", nargs="?", default="dist")
    check_package(parser.parse_args().output_dir)
