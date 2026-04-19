import os
import subprocess
import sys
import threading
import time
import webbrowser
import ctypes
import shutil
from pathlib import Path
from typing import Any

import pystray
import requests
from PIL import Image, ImageDraw


def get_project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


PROJECT_ROOT = get_project_root()


def load_env_config():
    """加载 .env 配置"""
    env_file = PROJECT_ROOT / '.env'
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file)
    
    host = os.getenv('HOST', '127.0.0.1')
    port = int(os.getenv('PORT', 8085))
    return host, port


HOST, PORT = load_env_config()
BACKEND_URL = f"http://{HOST}:{PORT}"
BACKEND_HEALTH_URL = f"{BACKEND_URL}/time"
BACKEND_LOG = PROJECT_ROOT / "tmp" / "tray_backend.log"
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_CONSOLE = 0x00000010
ERROR_ALREADY_EXISTS = 183
TRAY_MUTEX_NAME = "Global\\MaterialSearchTraySingleton"
AUTOSTART_SHORTCUT_NAME = "MaterialSearch Tray.lnk"


def acquire_single_instance_mutex():
    """仅允许一个托盘实例运行；返回 mutex 句柄，失败时返回 None。"""
    if os.name != "nt":
        return object()

    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, TRAY_MUTEX_NAME)
    if not mutex:
        return None
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        ctypes.windll.user32.MessageBoxW(
            None,
            "MaterialSearch 托盘已经在运行。",
            "MaterialSearch",
            0x00000040,
        )
        kernel32.CloseHandle(mutex)
        return None
    return mutex


def get_startup_dir() -> Path:
    startup = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return startup


def get_autostart_shortcut_path() -> Path:
    return get_startup_dir() / AUTOSTART_SHORTCUT_NAME


class TrayBackendManager:
    def __init__(self):
        self.process = None
        self.log_file = None
        self.icon: Any = None
        self._status_text = "未启动"
        self._status_lock = threading.Lock()
        self._stop_event = threading.Event()

    @property
    def status_text(self):
        with self._status_lock:
            return self._status_text

    @status_text.setter
    def status_text(self, value):
        with self._status_lock:
            self._status_text = value
        if self.icon is not None:
            self.icon.title = f"MaterialSearch - {value}"

    def get_pythonw(self) -> str:
        current_python = Path(sys.executable)
        pythonw = current_python.with_name("pythonw.exe")
        if pythonw.exists():
            return str(pythonw)
        return str(current_python)

    def get_backend_command(self) -> list[str]:
        if getattr(sys, "frozen", False):
            return [str(Path(sys.executable).resolve()), "--backend"]
        return [self.get_pythonw(), "-u", str(PROJECT_ROOT / "tray_app.py"), "--backend"]

    def ensure_log_dir(self):
        BACKEND_LOG.parent.mkdir(parents=True, exist_ok=True)

    def is_backend_running(self) -> bool:
        if self.process is not None and self.process.poll() is None:
            return True
        try:
            response = requests.get(BACKEND_HEALTH_URL, timeout=1, allow_redirects=False)
            return response.status_code in (200, 302)
        except Exception:
            return False

    def wait_backend_ready(self, timeout: int = 120):
        deadline = time.time() + timeout
        while time.time() < deadline and not self._stop_event.is_set():
            if self.process is not None and self.process.poll() is not None:
                return False
            try:
                response = requests.get(BACKEND_HEALTH_URL, timeout=1, allow_redirects=False)
                if response.status_code in (200, 302):
                    return True
            except Exception:
                pass
            time.sleep(1)
        return False

    def start_backend(self, icon=None, item=None):
        if self.is_backend_running():
            self.status_text = "后端已运行"
            return

        self.ensure_log_dir()
        self.log_file = open(BACKEND_LOG, "a", encoding="utf-8", buffering=1)
        self.status_text = "正在启动后端..."
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        self.process = subprocess.Popen(
            self.get_backend_command(),
            cwd=str(PROJECT_ROOT),
            stdout=self.log_file,
            stderr=self.log_file,
            creationflags=CREATE_NO_WINDOW,
            env=env,
        )

        def _wait_ready():
            if self.wait_backend_ready():
                self.status_text = "后端运行中"
            else:
                self.status_text = "后端启动失败，请查看 tmp/tray_backend.log"

        threading.Thread(target=_wait_ready, daemon=True).start()

    def toggle_backend(self, icon=None, item=None):
        if self.is_backend_running():
            self.stop_backend(icon, item)
        else:
            self.start_backend(icon, item)

    def stop_backend(self, icon=None, item=None):
        if self.process is None and not self.is_backend_running():
            self.status_text = "后端未运行"
            return

        self.status_text = "正在停止后端..."
        proc = self.process
        self.process = None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if self.log_file is not None:
            try:
                self.log_file.close()
            except Exception:
                pass
            self.log_file = None
        self.status_text = "后端已停止"

    def open_web(self, icon=None, item=None):
        if not self.is_backend_running():
            self.start_backend()
            threading.Thread(target=self._open_when_ready, daemon=True).start()
            return
        webbrowser.open(BACKEND_URL)

    def _open_when_ready(self):
        if self.wait_backend_ready():
            webbrowser.open(BACKEND_URL)

    def open_log(self, icon=None, item=None):
        self.ensure_log_dir()
        if not BACKEND_LOG.exists():
            BACKEND_LOG.touch()
        log_path = str(BACKEND_LOG).replace("'", "''")
        command = f"Get-Content -LiteralPath '{log_path}' -Encoding UTF8 -Wait -Tail 50"

        if shutil.which("wt"):
            subprocess.Popen(
                ["wt", "new-tab", "powershell", "-NoExit", "-Command", command],
                cwd=str(PROJECT_ROOT),
            )
            return

        subprocess.Popen(
            ["powershell.exe", "-NoExit", "-Command", command],
            cwd=str(PROJECT_ROOT),
            creationflags=CREATE_NEW_CONSOLE,
        )

    def open_project(self, icon=None, item=None):
        os.startfile(str(PROJECT_ROOT))

    def is_autostart_enabled(self) -> bool:
        return get_autostart_shortcut_path().exists()

    def toggle_autostart(self, icon=None, item=None):
        if self.is_autostart_enabled():
            self.disable_autostart(icon, item)
        else:
            self.enable_autostart(icon, item)

    def enable_autostart(self, icon=None, item=None):
        startup_dir = get_startup_dir()
        startup_dir.mkdir(parents=True, exist_ok=True)
        shortcut_path = get_autostart_shortcut_path()

        if getattr(sys, "frozen", False):
            target = str(Path(sys.executable).resolve())
            arguments = ""
        else:
            target = self.get_pythonw()
            arguments = f'"{PROJECT_ROOT / "tray_app.py"}"'

        shortcut_path_str = str(shortcut_path).replace("'", "''")
        target_str = target.replace("'", "''")
        arguments_str = arguments.replace("'", "''")
        project_root_str = str(PROJECT_ROOT).replace("'", "''")

        powershell_script = (
            "$WshShell = New-Object -ComObject WScript.Shell;"
            f"$Shortcut = $WshShell.CreateShortcut('{shortcut_path_str}');"
            f"$Shortcut.TargetPath = '{target_str}';"
            f"$Shortcut.Arguments = '{arguments_str}';"
            f"$Shortcut.WorkingDirectory = '{project_root_str}';"
            f"$Shortcut.IconLocation = '{target_str},0';"
            "$Shortcut.Save();"
        )
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", powershell_script],
            cwd=str(PROJECT_ROOT),
            check=True,
        )
        self.status_text = "已启用开机自启"

    def disable_autostart(self, icon=None, item=None):
        shortcut_path = get_autostart_shortcut_path()
        if shortcut_path.exists():
            shortcut_path.unlink()
        self.status_text = "已取消开机自启"

    def quit_app(self, icon, item):
        self._stop_event.set()
        self.stop_backend()
        icon.stop()

    def status_menu_text(self, item):
        return f"状态：{self.status_text}"


def create_icon_image(size: int = 64) -> Image.Image:
    image = Image.new("RGBA", (size, size), (37, 99, 235, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((6, 6, size - 6, size - 6), radius=14, fill=(37, 99, 235, 255))
    draw.rectangle((18, 18, 46, 46), outline=(255, 255, 255, 255), width=4)
    draw.line((24, 40, 32, 30, 40, 36), fill=(255, 255, 255, 255), width=4)
    return image


def run_tray():
    manager = TrayBackendManager()
    icon = pystray.Icon(
        "MaterialSearchTray",
        create_icon_image(),
        "MaterialSearch - 未启动",
        menu=pystray.Menu(
            pystray.MenuItem(lambda item: manager.status_menu_text(item), None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "后端运行",
                manager.toggle_backend,
                checked=lambda item: manager.is_backend_running(),
            ),
            pystray.MenuItem("打开网页", manager.open_web),
            pystray.MenuItem("查看日志", manager.open_log),
            pystray.MenuItem("打开项目目录", manager.open_project),
            pystray.MenuItem(
                "开机自启",
                manager.toggle_autostart,
                checked=lambda item: manager.is_autostart_enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", manager.quit_app),
        ),
    )
    manager.icon = icon
    icon.run()


def run_backend():
    from config import FLASK_DEBUG, HOST, LOG_LEVEL, PORT
    from main import init
    import routes

    init()
    import logging
    logging.getLogger('werkzeug').setLevel(LOG_LEVEL)
    routes.app.run(port=PORT, host=HOST, debug=FLASK_DEBUG)


if __name__ == "__main__":
    if "--backend" in sys.argv:
        run_backend()
    else:
        mutex = acquire_single_instance_mutex()
        if mutex is not None:
            try:
                run_tray()
            finally:
                if os.name == "nt":
                    ctypes.windll.kernel32.CloseHandle(mutex)
