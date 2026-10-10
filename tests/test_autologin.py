"""回归测试：所有网络、浏览器和注册表操作均隔离。"""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import authenticator
import autostart
import config
import main
import network
import prepare_release


def configured():
    cfg = copy.deepcopy(config.DEFAULT_CONFIG)
    cfg["account"].update(username="test-student", password=" test password ")
    return cfg


class ConfigTests(unittest.TestCase):
    def test_missing_relative_path_creates_valid_config(self):
        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                with contextlib.redirect_stdout(io.StringIO()):
                    cfg = config.load_config("settings.json")
                self.assertEqual(json.loads(Path("settings.json").read_text(encoding="utf-8")), cfg)
            finally:
                os.chdir(previous)

    def test_existing_partial_configuration_keeps_defaults_and_password(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(json.dumps({"account": {"password": " leading and trailing "}}), encoding="utf-8-sig")
            cfg = config.load_config(str(path))
        self.assertEqual(cfg["account"]["password"], " leading and trailing ")
        self.assertEqual(cfg["network"]["auth_timeout"], 15)

    def test_invalid_fields_are_rejected_without_logging_values(self):
        values = [None, [], {"network": None}, {"auto_login": {"check_interval": -1}},
                  {"auto_login": {"max_retry": True}}, {"browser": {"headless": "false"}},
                  {"network": {"portal_url": "http://portal:invalid/"}},
                  {"logging": {"log_dir": ""}}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            for value in values:
                with self.subTest(value=value):
                    path.write_text(json.dumps(value), encoding="utf-8")
                    with self.assertRaises(config.ConfigError):
                        config.load_config(str(path))

    def test_malformed_json_fails_instead_of_using_empty_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"password": "PRIVATE_SENTINEL",', encoding="utf-8")
            with self.assertRaises(config.ConfigError) as raised:
                config.load_config(str(path))
        self.assertNotIn("PRIVATE_SENTINEL", str(raised.exception))

    def test_interrupted_save_keeps_original_and_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            original = '{"original": true}'
            path.write_text(original, encoding="utf-8")
            with patch.object(config.os, "replace", side_effect=OSError("disk full")):
                with self.assertRaises(config.ConfigError):
                    config.save_config(str(path), configured())
            self.assertEqual(path.read_text(encoding="utf-8"), original)
            self.assertEqual(list(Path(directory).iterdir()), [path])


class FakeClock:
    def __init__(self):
        self.now = 0

    def monotonic(self):
        return self.now

    def sleep(self, delay):
        self.now += delay


class NetworkTests(unittest.TestCase):
    def test_primary_request_accepted_but_failed_connection_uses_backup(self):
        clock = FakeClock()
        requested = []
        def request(command, timeout):
            requested.append(command[-1])
            return types.SimpleNamespace(returncode=0)
        def current_ssid():
            return "backup" if requested and requested[-1] == "name=backup" else None
        with patch.object(network, "_run", side_effect=request), \
             patch.object(network, "get_current_ssid", side_effect=current_ssid), \
             patch.object(network.time, "monotonic", side_effect=clock.monotonic), \
             patch.object(network.time, "sleep", side_effect=clock.sleep):
            self.assertTrue(network.connect_wifi("primary", "backup", timeout=1))
        self.assertEqual(requested, ["name=primary", "name=backup"])

    def test_wifi_acceptance_without_connection_returns_failure(self):
        clock = FakeClock()
        with patch.object(network, "_run", return_value=types.SimpleNamespace(returncode=0)), \
             patch.object(network, "get_current_ssid", return_value=None), \
             patch.object(network.time, "monotonic", side_effect=clock.monotonic), \
             patch.object(network.time, "sleep", side_effect=clock.sleep):
            self.assertFalse(network.connect_wifi("primary", timeout=1))

    def test_existing_backup_is_kept_without_switching(self):
        with patch.object(network, "get_current_ssid", return_value="backup"), \
             patch.object(network, "_run") as run:
            self.assertTrue(network.connect_wifi("primary", "backup"))
        run.assert_not_called()

    def test_ssid_parser_ignores_bssid_and_supports_utf8(self):
        result = types.SimpleNamespace(returncode=0, stdout="BSSID : aa:bb:cc\nSSID : 校园网络\n".encode("utf-8"))
        with patch.object(network, "_run", return_value=result):
            self.assertEqual(network.get_current_ssid(), "校园网络")

    def test_portal_uses_explicit_and_protocol_ports(self):
        for url, expected in [("http://portal/", ("portal", 80)),
                              ("https://portal/", ("portal", 443)),
                              ("https://portal:8443/login", ("portal", 8443)),
                              ("http://[::1]:8080/", ("::1", 8080))]:
            with self.subTest(url=url), patch.object(network.socket, "create_connection", return_value=MagicMock()) as connect:
                self.assertTrue(network.can_reach_portal(url))
                self.assertEqual(connect.call_args.args[0], expected)

    def test_failed_probe_does_not_raise(self):
        with patch.object(network.socket, "create_connection", side_effect=OSError()):
            self.assertFalse(network.can_reach_portal("https://portal/"))
        self.assertFalse(network.can_reach_portal("http://portal:bad/"))

    def test_redirect_and_timeout_are_not_authenticated(self):
        with patch.object(network.requests, "get", return_value=Mock(status_code=302, headers={"Location": "http://portal/"})):
            self.assertFalse(network.is_authenticated("https://test.example/"))
        with patch.object(network.requests, "get", side_effect=network.requests.Timeout()):
            self.assertFalse(network.is_authenticated("https://test.example/"))


class AuthenticationTests(unittest.TestCase):
    def test_prepare_driver_opens_and_closes_without_portal_access(self):
        driver = Mock()
        cfg = configured()
        with patch.object(authenticator, "_build_driver", return_value=driver) as build:
            self.assertTrue(authenticator.prepare_driver(cfg, Mock()))
        self.assertTrue(build.call_args.args[0]["browser"]["headless"])
        self.assertFalse(cfg["browser"]["headless"])
        driver.get.assert_not_called()
        driver.quit.assert_called_once()

    def test_prepare_driver_failure_is_reported(self):
        with patch.object(authenticator, "_build_driver", side_effect=RuntimeError("offline")):
            self.assertFalse(authenticator.prepare_driver(configured(), Mock()))

    def test_invalid_explicit_driver_never_silently_downloads(self):
        cfg = configured()
        cfg["browser"]["driver_path"] = "missing-driver.exe"
        with patch.object(authenticator.os.path, "isfile", return_value=False), \
             patch.object(authenticator.webdriver, "Edge") as edge:
            with self.assertRaises(FileNotFoundError):
                authenticator._build_driver(cfg)
        edge.assert_not_called()

    def test_find_first_skips_hidden_match(self):
        hidden, visible = Mock(), Mock()
        hidden.is_displayed.return_value = False
        visible.is_displayed.return_value = True
        visible.is_enabled.return_value = True
        driver = Mock()
        driver.find_elements.return_value = [hidden, visible]
        self.assertIs(authenticator._find_first(driver, [("id", "user")], 1), visible)

    def test_unavailable_access_option_does_not_select_another_account_type(self):
        option = Mock(text="校园网学生接入")
        option.get_attribute.return_value = "student"
        select = Mock(options=[option])
        with patch.object(authenticator, "Select", return_value=select):
            with self.assertRaises(ValueError):
                authenticator._select_access_option(Mock(), "教职工接入")
        select.select_by_visible_text.assert_not_called()
        select.select_by_value.assert_not_called()

    def test_wrong_password_requests_manual_action_and_closes_browser(self):
        driver = Mock()
        driver.find_element.return_value.text = "用户名或密码错误"
        user, password, button = Mock(), Mock(), Mock()
        with patch.object(authenticator, "_build_driver", return_value=driver), \
             patch.object(authenticator, "_find_first", side_effect=[user, password, None, button]), \
             patch.object(authenticator.time, "sleep"):
            result = authenticator.authenticate(configured(), Mock())
        self.assertEqual(result, authenticator.AuthResult.MANUAL)
        password.send_keys.assert_called_once_with(" test password ")
        driver.quit.assert_called_once()

    def test_password_change_link_alone_does_not_stop_login(self):
        self.assertFalse(authenticator._requires_manual_action("欢迎使用校园网，修改密码，自助服务"))
        self.assertTrue(authenticator._requires_manual_action("首次登录，请先修改密码"))


class MainTests(unittest.TestCase):
    def test_prepare_driver_runs_while_already_online(self):
        with patch.object(sys, "argv", ["main.py", "--prepare-driver"]), \
             patch.object(config, "load_config", return_value=configured()), \
             patch.object(main, "setup_logger", return_value=Mock()), \
             patch.object(authenticator, "prepare_driver", return_value=True) as prepare, \
             patch.object(network, "is_authenticated") as probe:
            self.assertEqual(main.main(), main.RunResult.SUCCESS)
        prepare.assert_called_once()
        probe.assert_not_called()

    def test_failed_once_returns_failure_and_spaces_retries(self):
        cfg = configured()
        with patch.object(sys, "argv", ["main.py", "--once"]), \
             patch.object(config, "load_config", return_value=cfg), \
             patch.object(main, "setup_logger", return_value=Mock()), \
             patch.object(network, "is_authenticated", return_value=False), \
             patch.object(network, "can_reach_portal", return_value=True), \
             patch.object(authenticator, "authenticate", return_value=authenticator.AuthResult.RETRY) as authenticate, \
             patch.object(main.time, "sleep") as sleep:
            self.assertEqual(main.main(), main.RunResult.FAILED)
        self.assertEqual(authenticate.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [5, 5])

    def test_submitted_login_is_verified_before_success(self):
        with patch.object(network, "is_authenticated", side_effect=[False, False, False, True]), \
             patch.object(network, "can_reach_portal", return_value=True), \
             patch.object(authenticator, "authenticate", return_value=authenticator.AuthResult.SUBMITTED) as authenticate, \
             patch.object(main.time, "sleep"):
            self.assertEqual(main.once(configured(), Mock()), main.RunResult.SUCCESS)
        authenticate.assert_called_once()

    def test_manual_action_does_not_repeat_password_attempts(self):
        with patch.object(network, "is_authenticated", return_value=False), \
             patch.object(network, "can_reach_portal", return_value=True), \
             patch.object(authenticator, "authenticate", return_value=authenticator.AuthResult.MANUAL) as authenticate:
            self.assertEqual(main.once(configured(), Mock()), main.RunResult.MANUAL_ACTION)
        authenticate.assert_called_once()

    def test_wired_campus_connection_does_not_switch_wifi(self):
        with patch.object(network, "is_authenticated", side_effect=[False, False, True]), \
             patch.object(network, "can_reach_portal", return_value=True), \
             patch.object(network, "connect_wifi") as wifi, \
             patch.object(authenticator, "authenticate", return_value=authenticator.AuthResult.SUBMITTED), \
             patch.object(main.time, "sleep"):
            self.assertEqual(main.once(configured(), Mock()), main.RunResult.SUCCESS)
        wifi.assert_not_called()

    def test_outside_campus_is_distinct_from_authentication_failure(self):
        with patch.object(network, "is_authenticated", return_value=False), \
             patch.object(network, "can_reach_portal", return_value=False), \
             patch.object(network, "connect_wifi", return_value=False), \
             patch.object(authenticator, "authenticate") as authenticate:
            self.assertEqual(main.once(configured(), Mock()), main.RunResult.OUTSIDE_CAMPUS)
        authenticate.assert_not_called()

    def test_missing_credentials_do_not_open_browser(self):
        with patch.object(network, "is_authenticated", return_value=False), \
             patch.object(network, "can_reach_portal", return_value=True), \
             patch.object(authenticator, "authenticate") as authenticate:
            self.assertEqual(main.once(copy.deepcopy(config.DEFAULT_CONFIG), Mock()), main.RunResult.CONFIG_ERROR)
        authenticate.assert_not_called()

    def test_loop_backoff_is_capped_and_resets_after_success(self):
        cfg = configured()
        cfg["auto_login"]["max_backoff"] = 90
        results = [main.RunResult.FAILED, main.RunResult.FAILED, main.RunResult.SUCCESS,
                   main.RunResult.OUTSIDE_CAMPUS, main.RunResult.MANUAL_ACTION]
        with patch.object(main, "once", side_effect=results), patch.object(main.time, "sleep") as sleep:
            self.assertEqual(main.run_loop(cfg, Mock()), main.RunResult.MANUAL_ACTION)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [60, 90, 30, 30])

    def test_invalid_configuration_has_clear_exit_status(self):
        with patch.object(sys, "argv", ["main.py", "--once"]), \
             patch.object(config, "load_config", side_effect=config.ConfigError("invalid field")), \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main.main(), main.RunResult.CONFIG_ERROR)

    def test_setup_preserves_password_whitespace_and_uses_hidden_input(self):
        with patch.object(config, "load_config", return_value=configured()), \
             patch.object(config, "save_config") as save, \
             patch("builtins.input", side_effect=["test-student", "", ""]), \
             patch.object(main, "getpass", return_value=" secret "), \
             contextlib.redirect_stdout(io.StringIO()):
            main.run_setup("settings.json")
        self.assertEqual(save.call_args.args[1]["account"]["password"], " secret ")

    def test_autostart_forwards_absolute_config_and_headless(self):
        with patch.object(sys, "argv", ["main.py", "--config", "my settings.json", "--headless", "--install-autostart"]), \
             patch.object(autostart, "install", return_value=True) as install, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main.main(), main.RunResult.SUCCESS)
        self.assertEqual(install.call_args.args, (os.path.abspath("my settings.json"), True))

    def test_autostart_failure_is_not_success(self):
        with patch.object(sys, "argv", ["main.py", "--install-autostart"]), \
             patch.object(autostart, "install", return_value=False), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main.main(), main.RunResult.FAILED)

    def test_autostart_quotes_paths_and_preserves_flags(self):
        path = os.path.abspath("folder with spaces/settings.json")
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "executable", "C:\\Program Files\\JXUAS\\app.exe"):
            command = autostart._target_command(path, True)
        expected = subprocess.list2cmdline(["C:\\Program Files\\JXUAS\\app.exe", "--config", path, "--headless"])
        self.assertEqual(command, expected)


class ReleaseTests(unittest.TestCase):
    def test_build_stops_when_dependency_install_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            batch = (ROOT / "build.bat").read_text(encoding="utf-8")
            batch = batch.replace('set "BUILD_PYTHON=.venv\\Scripts\\python.exe"',
                                  'set "BUILD_PYTHON=%s"' % sys.executable)
            (root / "build.bat").write_bytes(batch.replace("\n", "\r\n").encode("utf-8"))
            (root / "pip.py").write_text("raise SystemExit(17)\n", encoding="utf-8")
            env = dict(os.environ, PYTHONPATH=str(root), PYTHONIOENCODING="utf-8")
            result = subprocess.run(["cmd", "/c", "build.bat", "--no-pause"], cwd=root,
                                    env=env, capture_output=True, text=True, encoding="utf-8",
                                    timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertNotIn("[2/4]", result.stdout)
            self.assertFalse((root / "dist").exists())

    def test_release_replaces_old_credentials_with_blank_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local = root / "source" / "config"
            local.mkdir(parents=True)
            (local / "config.json").write_text("PRIVATE_LOCAL_ACCOUNT", encoding="utf-8")
            (local / "config.example.json").write_text("{}", encoding="utf-8")
            output = root / "dist"
            (output / "config").mkdir(parents=True)
            (output / "config" / "config.json").write_text("OLD_RELEASE_PASSWORD", encoding="utf-8")
            with patch.object(prepare_release, "ROOT", root / "source"):
                prepare_release.prepare_release(output)
            released = (output / "config" / "config.json").read_text(encoding="utf-8")
            self.assertNotIn("PRIVATE_LOCAL_ACCOUNT", released)
            self.assertNotIn("OLD_RELEASE_PASSWORD", released)
            self.assertEqual(json.loads(released)["account"]["password"], "")
            self.assertEqual((local / "config.json").read_text(encoding="utf-8"), "PRIVATE_LOCAL_ACCOUNT")


if __name__ == "__main__":
    unittest.main()
