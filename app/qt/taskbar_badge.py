"""任务栏角标：显示今日未完成任务数。

模式 1（首选）：ITaskbarList3::SetOverlayIcon 原生 overlay（任务栏图标右下角小红圈）。
模式 2（降级）：把红圈数字直接画到窗口图标上（任务栏图标即窗口图标，效果一致）。

- count > 0：红色圆形角标 + 白色数字
- count == 0：清除角标
- 任何 COM/GDI 失败都静默降级，不影响主程序
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import byref, c_void_p

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

log = logging.getLogger("lighttodo")

_CLSCTX_INPROC_SERVER = 1
_COINIT_APARTMENTTHREADED = 2
_IMAGE_ICON = 2
_LR_LOADFROMFILE = 0x10
_SM_CXSMICON = 49
_SM_CYSMICON = 50

_CLSID_TaskbarList = "{56FDF344-FD6D-11d0-958A-006097C9A090}"
_IID_ITaskbarList3 = "{EA1AFB91-9E28-4B86-90C9-9E9F8A7EEFBF}"

# vtable 索引：IUnknown(0-2) + HrInit(3) ... SetOverlayIcon(11)
_VTBL_SET_OVERLAY_ICON = 11
_VTBL_HR_INIT = 3

BADGE_COLOR = "#c42b1c"  # Fluent 红


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid(text: str) -> _GUID:
    text = text.strip("{}")
    p1, p2, p3, p4, p5 = text.split("-")
    tail = bytes.fromhex(p4) + bytes.fromhex(p5)
    return _GUID(
        int(p1, 16),
        int(p2, 16),
        int(p3, 16),
        (ctypes.c_ubyte * 8).from_buffer_copy(tail),
    )


_HRESULT = ctypes.HRESULT
_FUNC_HR_INIT = ctypes.WINFUNCTYPE(_HRESULT, c_void_p, c_void_p)
_FUNC_SET_OVERLAY = ctypes.WINFUNCTYPE(_HRESULT, c_void_p, c_void_p, c_void_p, ctypes.c_wchar_p)


class TaskbarBadge:
    """窗口任务栏角标。每个主窗口持有一个实例。"""

    def __init__(self, base_icon: QIcon | None = None) -> None:
        self._base_icon = base_icon
        self._mode = "none"
        self._obj: c_void_p | None = None
        self._hr_init = None
        self._set_overlay = None
        self._hicon: c_void_p | None = None
        self._last_count: int | None = None
        self._init_com()

    # -------------------------------------------------- COM 初始化

    def _init_com(self) -> None:
        try:
            ole32 = ctypes.oledll.ole32
            try:
                ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
            except OSError:
                pass  # 已初始化过，忽略
            obj = c_void_p()
            ole32.CoCreateInstance(
                byref(_guid(_CLSID_TaskbarList)),
                None,
                _CLSCTX_INPROC_SERVER,
                byref(_guid(_IID_ITaskbarList3)),
                byref(obj),
            )
            if not obj:
                raise OSError("CoCreateInstance failed")
            vtable = ctypes.cast(obj, ctypes.POINTER(c_void_p)).contents.value
            if not vtable:
                raise OSError("bad vtable")
            entries = ctypes.cast(vtable, ctypes.POINTER(c_void_p * 14)).contents
            self._obj = obj
            self._hr_init = _FUNC_HR_INIT(entries[_VTBL_HR_INIT])
            self._set_overlay = _FUNC_SET_OVERLAY(entries[_VTBL_SET_OVERLAY_ICON])
            self._mode = "overlay"
        except Exception as exc:
            if self._base_icon is not None and not self._base_icon.isNull():
                self._mode = "icon"
                log.info("overlay 角标不可用(%s)，改用窗口图标角标", exc)
            else:
                self._mode = "none"
                log.warning("任务栏角标不可用: %s", exc)

    @property
    def mode(self) -> str:
        return self._mode

    # -------------------------------------------------- 角标绘制

    def _draw_badge(self, painter: QPainter, rect: QRect, count: int, big: bool) -> None:
        """在给定矩形内画红圈+白色数字。"""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(BADGE_COLOR))
        painter.drawEllipse(rect)
        painter.setPen(QColor("#ffffff"))
        font = QFont("Segoe UI")
        text = str(count) if count <= 99 else "99+"
        ratio = 0.62 if len(text) <= 2 else 0.5
        if not big:  # 小角标（窗口图标右下角）缩小一圈
            ratio *= 0.75
        font.setPixelSize(max(6, int(rect.height() * ratio)))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, text)
        painter.restore()

    def _badge_pixmap(self, count: int, size: int) -> QPixmap:
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        self._draw_badge(painter, pix.rect(), count, big=True)
        painter.end()
        return pix

    def _badged_window_icon(self, count: int) -> QIcon:
        """降级模式：在应用图标右下角画小红圈角标。"""
        base = QPixmap()
        if self._base_icon is not None and not self._base_icon.isNull():
            base = self._base_icon.pixmap(64, 64)
        if base.isNull():
            base = self._badge_pixmap(count, 64)
            return QIcon(base)
        pix = QPixmap(base.size())
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.drawPixmap(0, 0, base)
        side = max(12, base.width() // 2)
        rect = QRect(base.width() - side, base.height() - side, side, side)
        self._draw_badge(painter, rect, count, big=False)
        painter.end()
        return QIcon(pix)

    # -------------------------------------------------- overlay 模式辅助

    def _load_hicon(self, count: int) -> c_void_p | None:
        user32 = ctypes.windll.user32
        w = user32.GetSystemMetrics(_SM_CXSMICON) or 16
        h = user32.GetSystemMetrics(_SM_CYSMICON) or 16
        try:
            from .. import config

            path = config.data_dir() / "badge_tmp.ico"
            self._badge_pixmap(count, 32).save(str(path), "ICO")
            hicon = user32.LoadImageW(
                None, str(path), _IMAGE_ICON, w, h, _LR_LOADFROMFILE
            )
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
            return c_void_p(hicon) if hicon else None
        except Exception as exc:
            log.debug("生成角标图标失败: %s", exc)
            return None

    def _destroy_hicon(self) -> None:
        if self._hicon:
            try:
                ctypes.windll.user32.DestroyIcon(self._hicon)
            except Exception:
                pass
            self._hicon = None

    # -------------------------------------------------- 公开接口

    def set_count(self, hwnd: int, count: int, window=None) -> None:
        """更新角标数字；count<=0 时清除。window 用于降级模式 setWindowIcon。"""
        count = max(0, int(count))
        if count == self._last_count:
            return
        try:
            if self._mode == "overlay":
                self._hr_init(self._obj, c_void_p(hwnd))
                new_hicon = None
                if count > 0:
                    new_hicon = self._load_hicon(count)
                self._set_overlay(self._obj, c_void_p(hwnd), new_hicon, None)
                self._destroy_hicon()
                self._hicon = new_hicon
            elif self._mode == "icon" and window is not None:
                if count > 0:
                    window.setWindowIcon(self._badged_window_icon(count))
                else:
                    window.setWindowIcon(self._base_icon)
            else:
                return
            self._last_count = count
        except Exception as exc:
            log.debug("设置任务栏角标失败: %s", exc)
