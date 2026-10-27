import pytest
import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from test_storage import ROOT


class LifecycleTests(unittest.TestCase):
    def module(self, name):
        try:
            return importlib.import_module("scripts." + name)
        except ModuleNotFoundError as exc:
            self.fail(str(exc))

    def test_path_guard_and_backup_whitelist(self):
        m = self.module("maintenance")
        with tempfile.TemporaryDirectory(dir=ROOT) as d:
            root = Path(d)
            self.assertEqual(m.confined_path(root, root / "safe"), root / "safe")
            for target in (root, root / ".." / "escape"):
                with self.assertRaises(ValueError):
                    m.confined_path(root, target)
            (root / "config").mkdir()
            (root / "config" / "mansui.example.json").write_text("{}", encoding="utf-8")
            (root / "config" / "secrets.local.json").write_text(
                "SECRET_CANARY", encoding="utf-8"
            )
            archive = m.backup(root)
            import zipfile

            with zipfile.ZipFile(archive) as z:
                self.assertNotIn("secrets.local.json", " ".join(z.namelist()))
                self.assertNotIn(
                    b"SECRET_CANARY", b"".join(z.read(n) for n in z.namelist())
                )

    def test_pid_reuse_or_wrong_executable_refused(self):
        m = self.module("status")

        class Process:
            def create_time(self):
                return 100.0

            def exe(self):
                return r"E:\QQAgent\runtime\venv\Scripts\python.exe"

            def cmdline(self):
                return [self.exe(), r"E:\QQAgent\scripts\boot_astrbot.py"]

        record = {
            "pid": 999,
            "create_time": 100.0,
            "exe": Process().exe(),
            "marker": str(Path(r"E:\QQAgent\scripts\boot_astrbot.py")),
        }
        self.assertTrue(m.matches_process(record, Process()))
        for bad in (
            dict(record, create_time=99),
            dict(record, exe="other.exe"),
            dict(record, marker="other.py"),
        ):
            self.assertFalse(m.matches_process(bad, Process()))

    def test_configuration_roundtrip_stays_in_test_root_and_hides_key(self):
        from plugins.mansui_companion.settings import Settings, load_settings

        m = self.module("configure")
        with tempfile.TemporaryDirectory(dir=ROOT) as d:
            root = Path(d)
            cfg = Settings(
                "10001",
                "90001",
                ready=True,
                deepseek_api_key="TEST_ONLY_SECRET",
                onebot_token="ONEBOT_TEST",
                control_token="CONTROL_TEST",
            )
            m.save_configuration(root, cfg)
            loaded = load_settings(
                root / "config" / "mansui.local.json",
                root / "config" / "secrets.local.json",
            )
            self.assertEqual(loaded.deepseek_api_key, cfg.deepseek_api_key)
            self.assertNotIn(
                cfg.deepseek_api_key,
                (root / "config" / "mansui.local.json").read_text(encoding="utf-8"),
            )
            napcat = json.loads(
                (root / "data" / "napcat" / "config" / "napcat.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertFalse(napcat["fileLog"])
            self.assertFalse(napcat["consoleLog"])

    def test_ports_report_conflict_without_stopping_listener(self):
        m = self.module("preflight")
        import socket

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen()
            self.assertFalse(m.port_available(sock.getsockname()[1]))
            self.assertGreater(sock.fileno(), 0)


async def test_real_background_lifecycle_auth_duplicate_start_and_stop():
    import asyncio
    import subprocess
    import sys
    import aiohttp
    from scripts.configure import save_configuration
    from plugins.mansui_companion.settings import Settings
    import socket

    with tempfile.TemporaryDirectory(dir=ROOT) as directory:
        root = Path(directory)
        cfg = Settings(
            "10001",
            "90001",
            ready=True,
            deepseek_api_key="FAKE",
            onebot_token="FAKE_ONEBOT",
            control_token="SMOKE_CONTROL",
        )
        save_configuration(root, cfg)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        command = [
            sys.executable,
            "-B",
            r"E:\QQAgent\scripts\boot_astrbot.py",
            "--smoke-root",
            str(root),
            "--port",
            str(port),
        ]
        child = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            async with aiohttp.ClientSession() as client:
                for _ in range(100):
                    if child.poll() is not None:
                        pytest.fail(
                            "Smoke worker exited: "
                            + str(
                                (
                                    root / "runtime" / "state" / "last_error.json"
                                ).read_text()
                            )
                        )
                    try:
                        response = await client.get(
                            f"http://127.0.0.1:{port}/status",
                            headers={"Authorization": "Bearer SMOKE_CONTROL"},
                        )
                        if response.status == 200:
                            break
                    except aiohttp.ClientError:
                        pass
                    await asyncio.sleep(0.05)
                else:
                    pytest.fail("Smoke worker not ready")
                assert (await response.json())["service"] == "ready"
                async with client.get(f"http://127.0.0.1:{port}/status") as denied:
                    assert denied.status == 401
                second = subprocess.Popen(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                assert await asyncio.to_thread(second.wait, 10) == 1
                assert child.poll() is None
                async with client.post(
                    f"http://127.0.0.1:{port}/stop",
                    headers={"Authorization": "Bearer SMOKE_CONTROL"},
                ) as stopped:
                    assert stopped.status == 200
                assert await asyncio.to_thread(child.wait, 10) == 0
                assert not (root / "runtime" / "state" / "process.json").exists()
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(10)


def test_windows_job_closes_only_owned_child():
    import sys
    import psutil
    from scripts.boot_astrbot import launch_owned

    job, pid = launch_owned(
        sys.executable,
        ["-B", "-c", "import time; time.sleep(30)"],
        dict(os.environ),
        r"E:\QQAgent\runtime\test-state",
    )
    child = psutil.Process(pid)
    assert child.is_running()
    job.Close()
    child.wait(10)
    assert psutil.Process(os.getpid()).is_running()
