"""轻待办 · 便携版待办清单

直接双击本文件即可运行（需要本机已安装带 tkinter 的 Python 3.11+）。
也可以用 打包.bat 生成单文件 exe，exe 与 data 目录放在同一处即为便携版。
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.application import run  # noqa: E402

if __name__ == "__main__":
    run()
