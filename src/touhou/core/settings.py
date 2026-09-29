"""玩家设置及其持久化。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class Settings:
    bgmVolume: int = 7
    soundVolume: int = 8
    fullscreen: bool = False
    cheater: bool = False


def settingsPath() -> Path:
    """返回当前用户的设置文件位置，不依赖项目安装目录。"""
    appData = os.environ.get("APPDATA")
    if appData:
        return Path(appData) / "TouhouProject" / "settings.json"
    return Path.home() / ".touhou-project" / "settings.json"


def loadSettings(path: Path | None = None) -> Settings:
    """读取并校验设置；坏文件不会阻止游戏启动。"""
    source = path or settingsPath()
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Settings()
    if not isinstance(raw, dict):
        return Settings()

    defaults = Settings()
    return Settings(
        bgmVolume=_volume(raw.get("bgmVolume"), defaults.bgmVolume),
        soundVolume=_volume(raw.get("soundVolume"), defaults.soundVolume),
        fullscreen=_boolean(raw.get("fullscreen"), defaults.fullscreen),
        cheater=_boolean(raw.get("cheater"), defaults.cheater),
    )


def saveSettings(settings: Settings, path: Path | None = None) -> None:
    """以替换方式保存，避免中断写入留下半个 JSON。"""
    destination = path or settingsPath()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            {
                "bgmVolume": settings.bgmVolume,
                "soundVolume": settings.soundVolume,
                "fullscreen": settings.fullscreen,
                "cheater": settings.cheater,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)


def _volume(value: Any, default: int) -> int:
    if type(value) is not int:
        return default
    return max(0, min(10, value))


def _boolean(value: Any, default: bool) -> bool:
    if type(value) is not bool:
        return default
    return value
