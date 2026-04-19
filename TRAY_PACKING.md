# 托盘版打包说明

## 目标

将 `tray_app.py` 打包成一个无控制台窗口的 Windows 可执行程序：

- 运行后进入系统托盘
- 可启动/停止后端
- 保留浏览器前端
- 后端日志写入 `tmp/tray_backend.log`

## 打包前准备

1. 确保已创建虚拟环境 `.venv`
2. 安装项目依赖：

```bat
\.venv\Scripts\python.exe -m pip install -r requirements_windows.txt
```

3. 安装打包依赖（`build_tray.bat` 会自动安装）

## 一键打包

直接双击：

```bat
build_tray.bat
```

成功后输出目录在：

```text
dist\MaterialSearchTray\
```

主程序入口：

```text
dist\MaterialSearchTray\MaterialSearchTray.exe
```

## 运行方式

双击 `MaterialSearchTray.exe` 后：

- 不会弹黑框
- 会进入系统托盘
- 右键托盘图标可：
  - 启动后端
  - 停止后端
  - 打开网页
  - 查看日志
  - 打开项目目录
  - 退出

## 重要说明

### 1. `.env`
程序仍然从当前目录读取 `.env`。

如果你要整体移动打包目录，建议保持整个目录结构不变。

通常目录结构会像这样：

```text
MaterialSearchTray/
├─ MaterialSearchTray.exe
├─ _internal/
│  ├─ *.dll
│  ├─ static/
│  └─ ...
├─ .env
└─ tmp/
```

其中：

- 根目录：放程序入口、`.env`、日志目录等
- `_internal/`：放依赖和静态资源

如果你要把程序拷到别的地方运行，建议把这些内容一起带走：

- `MaterialSearchTray.exe`
- `_internal`
- `.env`

### 2. 模型文件
本打包脚本**不会把 HuggingFace 模型一起塞进 exe**，否则体积会非常大。

建议：

- 首次在开发环境下先跑过一次，让模型下载完成
- 运行打包版时继续复用本机已有缓存

### 3. 静态资源
`static/` 已通过 `tray_app.spec` 一起打进 exe，浏览器前端页面可正常加载。

### 4. 日志
后端日志输出到：

```text
tmp\tray_backend.log
```

如果启动失败，优先看这个文件。

### 5. ffmpeg
如果你后续还要视频相关功能，仍然需要系统里有 ffmpeg，或自行放到 PATH 中。
