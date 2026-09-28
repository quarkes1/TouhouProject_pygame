"""玩家设置的加载、校验与保存。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from touhou.core.settings import Settings, loadSettings, saveSettings, settingsPath


def testDefaultSettingsMatchThePlayableStartingPoint():
    assert Settings() == Settings(bgmVolume=7, soundVolume=8, fullscreen=False)


def testSettingsPathUsesAppDataWhenAvailable(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert settingsPath() == tmp_path / "TouhouProject" / "settings.json"


def testSettingsPathFallsBackToTheUserDirectory(monkeypatch, tmp_path):
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert settingsPath() == tmp_path / ".touhou-project" / "settings.json"


def testMissingSettingsUseDefaults(tmp_path):
    assert loadSettings(tmp_path / "missing.json") == Settings()


@pytest.mark.parametrize("content", ["{broken", "[]", "null"])
def testMalformedSettingsUseDefaults(tmp_path, content):
    path = tmp_path / "settings.json"
    path.write_text(content, encoding="utf-8")
    assert loadSettings(path) == Settings()


def testMissingFieldsKeepTheirDefaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"bgmVolume": 4}', encoding="utf-8")
    assert loadSettings(path) == Settings(bgmVolume=4, soundVolume=8, fullscreen=False)


def testSettingsAreClampedAndRoundTrip(tmp_path):
    path = tmp_path / "nested" / "settings.json"
    path.parent.mkdir()
    path.write_text('{"bgmVolume": 99, "soundVolume": -2, "fullscreen": true}', encoding="utf-8")

    loaded = loadSettings(path)

    assert loaded == Settings(bgmVolume=10, soundVolume=0, fullscreen=True)
    saveSettings(loaded, path)
    assert loadSettings(path) == loaded


def testBooleanAndStringVolumesDoNotMasqueradeAsNumbers(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"bgmVolume": true, "soundVolume": "4", "fullscreen": 1}', encoding="utf-8")
    assert loadSettings(path) == Settings()


def testSaveCreatesParentsAndLeavesNoTemporaryFile(tmp_path):
    path = tmp_path / "new" / "settings.json"

    saveSettings(Settings(bgmVolume=2, soundVolume=3, fullscreen=True), path)

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "bgmVolume": 2,
        "soundVolume": 3,
        "fullscreen": True,
    }
    assert not path.with_suffix(".json.tmp").exists()
