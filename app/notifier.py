"""Windows 通知：原生 Toast（PowerShell + WinRT），失败时回落到托盘气泡。"""

from __future__ import annotations

import base64
import shutil
import subprocess
import sys
import tempfile
import winreg
from pathlib import Path
from typing import Callable

from . import config

CREATE_NO_WINDOW = 0x08000000

# 纯 ASCII 脚本，参数用 base64 传，避免任何编码问题
TOAST_PS = r"""
param(
    [Parameter(Mandatory=$true)][string]$AppId,
    [Parameter(Mandatory=$true)][string]$TitleB64,
    [Parameter(Mandatory=$true)][string]$BodyB64,
    [int]$Sound = 1
)
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

$title = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($TitleB64))
$body = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($BodyB64))
$escTitle = [System.Security.SecurityElement]::Escape($title)
$escBody = [System.Security.SecurityElement]::Escape($body)
if ($Sound -eq 1) {
    $audio = '<audio src="ms-winsoundevent:Notification.Reminder"/>'
} else {
    $audio = '<audio silent="true"/>'
}
$xml = @"
<toast>
  <visual>
    <binding template="ToastGeneric">
      <text>$escTitle</text>
      <text>$escBody</text>
    </binding>
  </visual>
  $audio
</toast>
"@
$doc = New-Object Windows.Data.Xml.Dom.XmlDocument
$doc.LoadXml($xml)
$toast = New-Object Windows.UI.Notifications.ToastNotification $doc
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($AppId)
$notifier.Show($toast)
Write-Output 'OK'
"""


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _find_powershell() -> str | None:
    if sys.platform != "win32":
        return None
    candidate = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
    if candidate.exists():
        return str(candidate)
    found = shutil.which("powershell.exe") or shutil.which("powershell")
    return found


class Notifier:
    def __init__(self, icon_path: str | Path, app_id: str = config.APP_ID):
        self.icon_path = Path(icon_path)
        self.app_id = app_id
        self.last_error = ""
        self._fallback: Callable[[str, str], None] | None = None
        self._powershell = _find_powershell()
        self._script = Path(tempfile.gettempdir()) / "lighttodo_toast.ps1"
        self._register_aumid()
        self._write_script()

    # -------------------------------------------------- 准备

    def _register_aumid(self) -> None:
        """注册 AppUserModelID，让通知显示"轻待办"而不是 PowerShell。"""
        try:
            key = winreg.CreateKey(
                winreg.HKEY_CURRENT_USER, rf"Software\Classes\AppUserModelId\{self.app_id}"
            )
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, config.APP_NAME)
            if self.icon_path.exists():
                winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, str(self.icon_path))
            winreg.CloseKey(key)
        except OSError as exc:
            self.last_error = f"AUMID 注册失败: {exc}"

    def _write_script(self) -> None:
        try:
            current = self._script.read_text(encoding="utf-8") if self._script.exists() else ""
            if current != TOAST_PS:
                self._script.write_text(TOAST_PS, encoding="utf-8")
        except OSError as exc:
            self.last_error = f"通知脚本写入失败: {exc}"

    def set_fallback(self, func: Callable[[str, str], None] | None) -> None:
        self._fallback = func

    # -------------------------------------------------- 发送

    def show(self, title: str, body: str, sound: bool = True) -> bool:
        title = (title or config.APP_NAME)[:120]
        body = (body or "")[:240]
        if self._powershell and self._toast(title, body, sound):
            return True
        if self._fallback is not None:
            try:
                self._fallback(title, body)
                return True
            except Exception as exc:  # pragma: no cover - 兜底路径
                self.last_error = f"托盘气泡失败: {exc}"
        return False

    def _toast(self, title: str, body: str, sound: bool) -> bool:
        cmd = [
            self._powershell,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self._script),
            "-AppId",
            self.app_id,
            "-TitleB64",
            _b64(title),
            "-BodyB64",
            _b64(body),
            "-Sound",
            "1" if sound else "0",
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=20,
                creationflags=CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.last_error = f"通知调用失败: {exc}"
            return False

        if proc.returncode == 0 and b"OK" in proc.stdout:
            return True

        detail = (proc.stderr or b"").decode("utf-8", "ignore").strip()
        self.last_error = f"notify failed rc={proc.returncode} {detail[:300]}"
        return False


if __name__ == "__main__":
    config.data_dir().mkdir(parents=True, exist_ok=True)
    icon = config.data_dir() / "icon.ico"
    from .icon import runtime_icon

    n = Notifier(runtime_icon(icon))
    ok = n.show("轻待办 · 测试通知", "这是一条测试提醒，说明通知通道可用。")
    print("shown:", ok, n.last_error)
