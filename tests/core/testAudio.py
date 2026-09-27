"""BGM、音效与无声降级。"""

import pygame
import pytest

from touhou.core.audio import AudioManager
from touhou.core.settings import Settings


@pytest.fixture
def audioManager():
    manager = AudioManager(Settings())
    yield manager
    manager.close()


def testAudioManagerLoadsEveryNamedSound(audioManager):
    assert set(audioManager.sounds) == {
        "select",
        "confirm",
        "cancel",
        "shot",
        "bomb",
        "damage",
        "death",
    }


def testMusicAndSoundUseIndependentVolumes(audioManager):
    audioManager.applySettings(Settings(bgmVolume=3, soundVolume=8))
    assert pygame.mixer.music.get_volume() == pytest.approx(0.3, abs=0.02)
    assert audioManager.sounds["confirm"].get_volume() == pytest.approx(0.8, abs=0.02)


def testReplayingCurrentMusicDoesNotReloadIt(audioManager, monkeypatch):
    loaded = []
    played = []
    monkeypatch.setattr(pygame.mixer.music, "load", lambda path: loaded.append(path))
    monkeypatch.setattr(pygame.mixer.music, "play", lambda loops: played.append(loops))

    audioManager.playMusic("title")
    audioManager.playMusic("title")

    assert len(loaded) == 1
    assert played == [-1]


@pytest.mark.parametrize("method", ["playMusic", "playSound"])
def testUnknownSymbolicNameIsRejected(audioManager, method):
    with pytest.raises(KeyError):
        getattr(audioManager, method)("missing")


def testMixerFailureFallsBackToSafeSilence(monkeypatch):
    pygame.mixer.quit()
    with monkeypatch.context() as context:
        context.setattr(
            pygame.mixer,
            "init",
            lambda: (_ for _ in ()).throw(pygame.error("no device")),
        )

        audio = AudioManager(Settings())
        audio.playMusic("title")
        audio.playSound("confirm")
        audio.applySettings(Settings(bgmVolume=0, soundVolume=0))
        audio.stopMusic()
        audio.close()

        assert not audio.available
    pygame.mixer.init()
