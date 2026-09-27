"""集中管理 BGM 与音效，并在没有音频设备时安全静音。"""

from __future__ import annotations

import pygame

from touhou.core.paths import assetPath
from touhou.core.settings import Settings

MUSIC_PATHS = {
    "title": ("music", "01.-A-Dream-that-is-more-Scarlet-than-Red_1.wav"),
    "stage": ("music", "08.-Voile_-the-Magic-Library_1.wav"),
    "boss": ("music", "09.-Locked-Girl-_-The-Girl_s-Secret-Room.wav"),
}

SOUND_PATHS = {
    "select": ("music", "sounds", "22-select00.wav"),
    "confirm": ("music", "sounds", "16-ok00.wav"),
    "cancel": ("music", "sounds", "01-cancel00.wav"),
    "shot": ("music", "sounds", "08-gun00.wav"),
    "bomb": ("music", "sounds", "18-plst00.wav"),
    "damage": ("music", "sounds", "03-damage00.wav"),
    "death": ("music", "sounds", "17-pldead00.wav"),
}


class AudioManager:
    __slots__ = ("available", "currentMusic", "settings", "sounds")

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.available = False
        self.currentMusic: str | None = None
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init()
            self.sounds = {
                name: pygame.mixer.Sound(str(assetPath(*parts)))
                for name, parts in SOUND_PATHS.items()
            }
            self.available = True
            self.applySettings(settings)
        except pygame.error:
            # 无声设备常见于远程桌面和 CI。声音不是游戏可运行的前提。
            self.sounds.clear()

    def applySettings(self, settings: Settings) -> None:
        self.settings = settings
        if not self.available:
            return
        pygame.mixer.music.set_volume(settings.bgmVolume / 10.0)
        soundVolume = settings.soundVolume / 10.0
        for sound in self.sounds.values():
            sound.set_volume(soundVolume)

    def playMusic(self, name: str) -> None:
        parts = MUSIC_PATHS[name]
        if not self.available or self.currentMusic == name:
            return
        pygame.mixer.music.load(str(assetPath(*parts)))
        pygame.mixer.music.play(-1)
        self.currentMusic = name

    def stopMusic(self) -> None:
        if self.available:
            pygame.mixer.music.stop()
        self.currentMusic = None

    def playSound(self, name: str) -> None:
        if name not in SOUND_PATHS:
            raise KeyError(name)
        if self.available:
            self.sounds[name].play()

    def close(self) -> None:
        self.stopMusic()
