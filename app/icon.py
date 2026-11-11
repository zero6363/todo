"""应用图标：运行时用 Pillow 生成，保证便携版不需要外部图片。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def _hex(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def make_icon(size: int = 256, top: str = "#5B8DFF", bottom: str = "#2B5EE2") -> Image.Image:
    """圆角方块 + 白色对勾。"""
    scale = 4
    s = size * scale
    base = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    # 竖向渐变
    c_top, c_bottom = _hex(top), _hex(bottom)
    gradient = Image.new("RGBA", (s, s))
    px = gradient.load()
    for y in range(s):
        t = y / max(s - 1, 1)
        color = tuple(int(c_top[i] + (c_bottom[i] - c_top[i]) * t) for i in range(3))
        for x in range(s):
            px[x, y] = (*color, 255)

    # 圆角遮罩
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.24), fill=255)
    base.paste(gradient, (0, 0), mask)

    # 对勾
    draw = ImageDraw.Draw(base)
    width = max(int(s * 0.085), 2)
    points = [(s * 0.26, s * 0.53), (s * 0.43, s * 0.70), (s * 0.75, s * 0.32)]
    draw.line(points, fill=(255, 255, 255, 255), width=width, joint="curve")
    for p in (points[0], points[-1]):
        r = width / 2
        draw.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=(255, 255, 255, 255))

    return base.resize((size, size), Image.LANCZOS)


def save_ico(path: str | Path, sizes: tuple[int, ...] = (16, 24, 32, 48, 64, 128, 256)) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    img = make_icon(256)
    img.save(path, format="ICO", sizes=[(s, s) for s in sizes])
    return path


def runtime_icon(path: str | Path) -> Path:
    """把图标复制到可写的数据目录，供 AUMID 注册与窗口图标长期稳定引用。"""
    path = Path(path)
    if not path.exists():
        save_ico(path)
    return path


def check_circle(size: int = 20, state: str = "normal") -> Image.Image:
    """任务行的圆形勾选框（4 倍超采样，缩放后边缘平滑）。

    state: normal / hover / done
    """
    scale = 4
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = int(1.5 * scale)
    box = (pad, pad, s - pad, s - pad)
    width = max(int(1.5 * scale), 2)

    if state == "done":
        draw.ellipse(box, fill=(58, 111, 247, 255), outline=(58, 111, 247, 255))
        stroke = max(int(s * 0.085), 2)
        points = [(s * 0.30, s * 0.52), (s * 0.44, s * 0.66), (s * 0.71, s * 0.35)]
        draw.line(points, fill=(255, 255, 255, 255), width=stroke, joint="curve")
        for point in (points[0], points[-1]):
            r = stroke / 2
            draw.ellipse(
                (point[0] - r, point[1] - r, point[0] + r, point[1] + r),
                fill=(255, 255, 255, 255),
            )
    else:
        outline = (58, 111, 247, 255) if state == "hover" else (198, 204, 214, 255)
        draw.ellipse(box, fill=(0, 0, 0, 0), outline=outline, width=width)

    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    import sys

    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
    print(save_ico(target))
