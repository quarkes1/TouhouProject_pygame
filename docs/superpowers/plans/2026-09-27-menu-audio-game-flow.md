# Menu, Audio, and Complete Game Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Touhou-style title/options/pause/result flow, persistent settings, working BGM and sound effects, and ship the result in the standalone Windows package.

**Architecture:** Keep gameplay rules in the existing `Game` session and add an application-level scene controller around it. Pure settings and menu models stay independently testable; pygame audio is isolated behind `AudioManager`; `main.py` owns transitions and recreates sessions for restart.

**Tech Stack:** Python 3.13, pygame-ce 2.5.8+, JSON, pytest, PyInstaller

**Spec:** `docs/superpowers/specs/2026-09-27-menu-audio-game-flow-design.md`

## Global Constraints

- Use `lowerCamelCase` for functions, methods, variables, and parameters; `PascalCase` for classes.
- Do not add numpy or another UI/audio dependency.
- No machine-specific absolute paths in code or documentation.
- Menus use event edges; gameplay movement and shooting continue to use polled input.
- Window mode is resizable; the 640×480 logical canvas keeps its aspect ratio and is centered.
- Menu/options/result scenes never advance the fixed-step gameplay simulation.
- Audio initialization failure must produce a playable silent game.
- Only implemented menu entries are visible.
- Run tests with the project interpreter selected by the user or IDE, expressed in docs as `python`.

## Review Focus

- Corrupt or partially written settings JSON must not prevent startup; Task 1 pins fallback and clamping.
- A held/repeated key must not execute multiple menu actions in one event batch; Task 2 pins one action per event.
- Scene transitions must clear accumulator debt and queued bomb input; Task 4 pins both.
- Missing audio device or missing mixer initialization must leave all audio methods safe; Task 3 pins silent fallback.
- Stage completion must not trigger during a temporary gap between enemy waves; Task 5 pins all schedule cursors and duration.

---

### Task 1: Persistent settings

**Files:**
- Create: `src/touhou/core/settings.py`
- Create: `tests/core/testSettings.py`

**Interfaces:**
- Produces: `Settings(bgmVolume: int = 7, soundVolume: int = 8, fullscreen: bool = False)`
- Produces: `settingsPath() -> Path`
- Produces: `loadSettings(path: Path | None = None) -> Settings`
- Produces: `saveSettings(settings: Settings, path: Path | None = None) -> None`

- [ ] **Step 1: Write failing settings tests**

Cover default values, `%APPDATA%` selection, fallback to the user directory, missing file, corrupt JSON,
missing fields, numeric clamping to 0..10, rejecting booleans as volume numbers, and save/reload equality.

```python
def testCorruptSettingsFallBackToDefaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{broken", encoding="utf-8")
    assert loadSettings(path) == Settings()


def testSettingsAreClampedAndRoundTrip(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"bgmVolume": 99, "soundVolume": -2, "fullscreen": true}')
    loaded = loadSettings(path)
    assert loaded == Settings(bgmVolume=10, soundVolume=0, fullscreen=True)
    saveSettings(loaded, path)
    assert loadSettings(path) == loaded
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest tests/core/testSettings.py -q`
Expected: collection fails because `touhou.core.settings` does not exist.

- [ ] **Step 3: Implement the immutable settings model and JSON persistence**

Use a frozen slotted dataclass. Save through a sibling temporary file followed by `Path.replace()` so an
interrupted write does not leave half JSON. Catch `OSError`, `json.JSONDecodeError`, and shape/type errors
when loading, returning validated defaults.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/core/testSettings.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/touhou/core/settings.py tests/core/testSettings.py
git commit -m "feat: add persistent game settings"
```

### Task 2: Touhou-style menu model and rendering

**Files:**
- Create: `src/touhou/ui/menu.py`
- Create: `tests/ui/testMenu.py`

**Interfaces:**
- Produces: `MenuItem(label: str, action: str)`
- Produces: `Menu(items: tuple[MenuItem, ...], selectedIndex: int = 0)`
- Produces: `Menu.handleKey(key: int) -> str | None`
- Produces: `OptionsMenu(settings: Settings)` with `handleKey(key: int) -> tuple[str | None, Settings]`
- Produces: `drawTitle(canvas: pygame.Surface, background: pygame.Surface, menu: Menu) -> None`
- Produces: `drawOverlayMenu(canvas: pygame.Surface, title: str, menu: Menu) -> None`
- Consumes: existing font asset through `assetPath()`.

- [ ] **Step 1: Write failing menu behavior tests**

```python
def testMenuWrapsAndConfirms():
    menu = Menu((MenuItem("开始游戏", "start"), MenuItem("退出", "quit")))
    assert menu.handleKey(pygame.K_UP) is None
    assert menu.selectedIndex == 1
    assert menu.handleKey(pygame.K_z) == "quit"


def testOptionsAdjustAndReturnUpdatedSettings():
    menu = OptionsMenu(Settings(bgmVolume=7))
    action, changed = menu.handleKey(pygame.K_RIGHT)
    assert action == "settingsChanged"
    assert changed.bgmVolume == 8
```

Also test Enter confirmation, X/Esc back, 0/10 bounds, fullscreen toggle, and that one key event changes
one step only. Add a pixel-level smoke assertion proving selected and unselected labels render differently.

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest tests/ui/testMenu.py -q`
Expected: collection fails because `touhou.ui.menu` does not exist.

- [ ] **Step 3: Implement menu state and rendering**

Use the title wallpaper, existing DFPPOPCorn font, warm-white labels, red selected label, and a small
horizontal selected offset. Keep event handling separate from drawing.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/ui/testMenu.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/touhou/ui/menu.py tests/ui/testMenu.py
git commit -m "feat: add title and options menus"
```

### Task 3: Audio manager with silent fallback

**Files:**
- Create: `src/touhou/core/audio.py`
- Create: `tests/core/testAudio.py`

**Interfaces:**
- Produces: `AudioManager(settings: Settings)`
- Produces methods: `applySettings(settings)`, `playMusic(name)`, `stopMusic()`, `playSound(name)`, `close()`
- Music names: `title`, `stage`, `boss`
- Sound names: `select`, `confirm`, `cancel`, `shot`, `bomb`, `damage`, `death`

- [ ] **Step 1: Write failing audio tests**

Use real pygame mixer under the configured dummy audio driver and tiny repository WAV assets. Assert:

```python
def testMusicAndSoundUseIndependentVolumes(audioManager):
    audioManager.applySettings(Settings(bgmVolume=3, soundVolume=8))
    assert pygame.mixer.music.get_volume() == pytest.approx(0.3)
    assert audioManager.sounds["confirm"].get_volume() == pytest.approx(0.8)


def testMixerFailureFallsBackToSafeSilence(monkeypatch):
    monkeypatch.setattr(pygame.mixer, "init", lambda: (_ for _ in ()).throw(pygame.error("no device")))
    audio = AudioManager(Settings())
    audio.playMusic("title")
    audio.playSound("confirm")
    assert not audio.available
```

Also assert replaying the current music does not reload it and unknown symbolic names raise `KeyError`.

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest tests/core/testAudio.py -q`
Expected: collection fails because `touhou.core.audio` does not exist.

- [ ] **Step 3: Implement AudioManager**

Map symbolic names to existing assets. Initialize mixer only if needed; catch `pygame.error` once and keep
all public methods as no-ops in silent mode. Convert setting levels with `level / 10.0`.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/core/testAudio.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/touhou/core/audio.py tests/core/testAudio.py
git commit -m "feat: add music and sound management"
```

### Task 4: Application scene controller and pause flow

**Files:**
- Modify: `src/touhou/main.py`
- Modify: `tests/testMain.py`

**Interfaces:**
- Produces: `Scene` enum with `TITLE`, `OPTIONS`, `PLAYING`, `PAUSED`, `GAME_OVER`, `STAGE_CLEAR`
- Produces: `Application(settingsPathOverride: Path | None = None)`
- Produces methods: `startGame()`, `restartGame()`, `returnToTitle()`, `handleEvents()`, `update()`, `render()`
- Changes: existing `Game` becomes one gameplay session and no longer owns process-level `running`.

- [ ] **Step 1: Write failing transition tests**

```python
def testApplicationStartsAtTitle(application):
    assert application.scene is Scene.TITLE
    assert application.game is None


def testEscapePausesAndContinuePreservesSession(application):
    application.startGame()
    session = application.game
    postKeydown(pygame.K_ESCAPE)
    application.handleEvents()
    assert application.scene is Scene.PAUSED
    postKeydown(pygame.K_z)
    application.handleEvents()
    assert application.scene is Scene.PLAYING
    assert application.game is session
```

Add tests for start, restart creates a different session, title return drops the session, quit works in all
scenes, paused update does not advance enemies/background, settings changes apply/save, and transitions
reset both accumulator pending seconds and bomb latch pending count. Add resize tests for larger, non-4:3,
and sub-640×480 windows: the destination rectangle stays centered, preserves aspect ratio, and never crops.

- [ ] **Step 2: Run selected tests and verify RED**

Run: `python -m pytest tests/testMain.py -q`
Expected: failures because `Application` and `Scene` do not exist and Escape still stops `Game`.

- [ ] **Step 3: Refactor main.py around Application**

Keep window/canvas/audio/settings on `Application`. Construct `Game` only in `startGame()` and
`restartGame()`. Create windowed displays with `pygame.RESIZABLE`, consume `VIDEORESIZE`, and compute a
centered destination rectangle for the fixed 640×480 canvas. Use integer enlargement when it fits and
proportional smooth downscaling only below logical size. Route event keys to the active menu or gameplay
pause transition. Keep the existing fixed-step order unchanged while `PLAYING`.

- [ ] **Step 4: Run main integration tests**

Run: `python -m pytest tests/testMain.py -q`
Expected: all pass after adapting old tests to construct a gameplay session fixture explicitly.

- [ ] **Step 5: Commit**

```bash
git add src/touhou/main.py tests/testMain.py
git commit -m "feat: add title options and pause scene flow"
```

### Task 5: Game Over, Stage Clear, and gameplay audio edges

**Files:**
- Modify: `src/touhou/main.py`
- Modify: `src/touhou/game/enemyField.py`
- Modify: `tests/testMain.py`
- Create: `tests/game/testEnemyField.py`

**Interfaces:**
- Produces: `EnemyField.scheduleComplete() -> bool`
- Produces: `Game.isStageClear() -> bool`
- Application observes `player.state is State.DEAD` and `game.isStageClear()` after each logic step.

- [ ] **Step 1: Write failing completion and death tests**

```python
def testLastDeathMovesToGameOver(application):
    application.startGame()
    application.game.player.state = State.DEAD
    application.update()
    assert application.scene is Scene.GAME_OVER


def testGapBetweenWavesIsNotStageClear(game):
    game.enemyField.active.clear()
    game.enemyField.spawnCursor = 0
    assert not game.isStageClear()
```

Add tests that all spawn cursors exhausted plus no active enemies plus elapsed time reaching level duration
does clear; Game Over and Stage Clear menus restart/return/quit; stage music starts with a new session;
boss music changes once on boss arrival; shot/bomb/damage/death sounds fire only on their event edges.

- [ ] **Step 2: Run selected tests and verify RED**

Run: `python -m pytest tests/testMain.py tests/game/testEnemyField.py -q`
Expected: missing completion APIs and result transitions fail.

- [ ] **Step 3: Implement completion predicates and audio edge observation**

`scheduleComplete()` checks both cursors, active list, and boss reference. `Game.isStageClear()` additionally
requires `elapsedFrames >= level.durationFrames`. Store previous player state, shot count, bomb count, and
boss reference in the application/session boundary to trigger sounds only on transitions.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/testMain.py tests/game/testEnemyField.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/touhou/main.py src/touhou/game/enemyField.py tests/testMain.py tests/game/testEnemyField.py
git commit -m "feat: complete game over and stage clear loops"
```

### Task 6: Documentation, package, and executable acceptance

**Files:**
- Modify: `README.md`
- Modify: `dist/build.py` only if PyInstaller analysis reveals a missing dynamic module
- Modify: `tests/testBuild.py` if build configuration changes
- Generated: `dist/TouhouProject/`

**Interfaces:**
- The public run commands remain `python run.py` and `python dist/build.py`.

- [ ] **Step 1: Update the concise README**

Document the title/options/pause/result flow, controls, actual BGM/SE settings, settings file location, and
the requirement to distribute the whole onedir folder. Keep README under roughly 120 lines.

- [ ] **Step 2: Run the complete quality gate once**

Run:

```bash
python -m pytest -q
python -m ruff format --check .
python -m ruff check .
python -m mypy .
```

Expected: all product tests and configured gates pass. If existing out-of-scope `tools/` mypy findings remain,
record exact findings and separately verify `python -m mypy src/touhou run.py dist/build.py`.

- [ ] **Step 3: Rebuild the onedir package**

Run: `python dist/build.py`
Expected: `dist/TouhouProject/TouhouProject.exe` exists and PyInstaller reports the stage modules collected.

- [ ] **Step 4: Smoke-test from outside the repository**

Launch the executable with a temporary working directory. Verify title menu appears, start enters gameplay,
window drag-resizing keeps the picture centered without stretching, Esc opens pause, options visibly change
audio volume, full-screen can be entered and left, forced final death reaches Game Over, return reaches title,
and the process exits cleanly. Confirm the process remains alive for at least three seconds in the automated
smoke portion before manual interaction.

- [ ] **Step 5: Verify package contents and Git status**

Confirm `_internal/assets/music`, title background, fonts, level JSON, and `touhou.game.stage.level1` are in
the package/archive. Run `git diff --check` and ensure only intentional source changes remain uncommitted.

- [ ] **Step 6: Commit source and documentation**

```bash
git add README.md dist/build.py tests/testBuild.py
git commit -m "build: package complete menu and audio flow"
```

Generated `dist/TouhouProject/` remains ignored and is delivered as the local executable artifact.
