# 轻待办

Windows 上用的轻量待办清单，PySide6 + qfluentwidgets 写的 Fluent 风格界面，单文件 exe 便携运行，数据存在本地 SQLite。

## 下载

现成 exe 见 Releases：<https://github.com/zero6363/todo/releases/latest>
（`qing-daiban-v1.4.4.exe` 双击即用，首次启动在同目录生成 `data` 目录）。

## 功能

- **中文语义添加**：`十点开会`、`1小时后 关火`、`每三天十点 浇花`、`每周一 十点 周会`、`每月15号 交房租`、`!!` 标记优先级，输入框下方实时显示彩色胶囊（日期 / 重复 / 优先级）。
- **默认时间**：只写任务名默认排到今天 14:00；只写日期默认 14:00 到点提醒。
- **循环任务**：完成后自动生成下一次（每天 / 工作日 / 每周几 / 每月几号 / 每 N 天 / 每 N 周），过期补做会自动顺延到今天以后。
- **提醒**：应用内卡片提醒（右下角最多 3 张，多的排队）+ 系统通知 + 提示音，可稍后提醒（10/30/60 分钟或自定义）。
- **默认显示「全部」**：启动直接进入全部视图；任务栏图标带红色角标，显示今天还有几项未完成。
- **延期显示**：过期未完成会自动延续到今天，列表和详情里显示「已延期 N 次 · 延期至 今天 14:00」和原定日期。
- **清单 / 优先级 / 搜索 / 拖拽排序 / 托盘 / 开机自启 / 快捷键**。

## 目录

```
app/                 主程序（Python 包）
  qt/                PySide6 界面层
  db.py              SQLite 存储与迁移
  utils.py           中文时间语义解析、循环规则推算
  reminder.py        到点扫描、顺延
  notifier.py        系统通知
  config.py          版本号、默认值
轻待办.pyw            入口（无控制台）
轻待办.spec           PyInstaller 打包配置
打包.bat              一键打包单文件 exe
启动.bat              源码方式启动
assets/icon.ico       图标
使用说明.txt           给最终用户看的说明书
旧版tk界面/            早期 tkinter 版本，仅留档
```

## 跑起来

```bat
pip install PySide6-Fluent-Widgets pillow pyinstaller
启动.bat
```

或直接 `py -3.15 轻待办.pyw`。

## 打包

```bat
打包.bat
```

产物在 `dist\轻待办.exe`（单文件、无控制台，约 90MB）。首次运行会在 exe 同级目录生成 `data\` 存放数据库和日志。

## 数据

`data/todo.db`（SQLite）；`data/app.log` 记日志。整个 `data` 目录可以随 exe 一起搬走。
