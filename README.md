# TouhouProject

用 Python 和 pygame-ce 制作的东方 Project 教学版弹幕游戏。

目前已有完整的一关基础流程：自机移动与射击、低速模式、炸弹、残机、敌机波次、
弹幕、碰撞、中 BOSS、HUD 和关卡数据加载。

## 运行源码

需要 Python 3.13 或更高版本。

```bash
python -m pip install -r requirements.txt
python run.py
```

开发依赖：

```bash
python -m pip install -e ".[dev]"
```

## 运行打包版

打开：

```text
dist/TouhouProject/TouhouProject.exe
```

发布时必须复制整个 `dist/TouhouProject/` 文件夹，不能只复制 exe。

## 操作

| 按键 | 功能 |
| --- | --- |
| 方向键 | 移动 |
| Z | 射击 / 确认 |
| X | 炸弹 |
| Shift | 低速移动 |
| Esc | 暂停 / 返回 |

## 打包

先安装开发依赖，然后运行：

```bash
python dist/build.py
```

产物位于 `dist/TouhouProject/`。打包脚本会包含 `assets/`，并显式收集关卡数据动态
加载的 BOSS 脚本模块。

## 常用开发命令

```bash
python -m pytest -q
python -m ruff check .
python -m mypy .
```

## 项目结构

```text
assets/          图片、音频、字体与关卡数据
src/touhou/      游戏源码
tests/           自动化测试
tools/           关卡迁移等开发工具
dist/build.py    PyInstaller 打包入口
docs/DESIGN.md   设计与接口约定
```

## 版权说明

本项目是非商业同人教学项目，不是东方原作的移植或逆向工程。东方 Project 相关版权
归上海爱丽丝幻乐团（ZUN）所有。

素材与部分关卡设计参考
[NumPix/pygame-touhou](https://github.com/NumPix/pygame-touhou)，按其 MIT 协议保留署名。
详细说明见 `LICENSE`。
