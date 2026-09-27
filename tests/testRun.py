"""仓库根目录那个 `run.py`（免安装的启动脚本）。

这个文件守的是**它承诺给玩家的那几句话**：一条命令、三平台通用、不写死路径、
报错要说人话。这些承诺全都不是「跑起来才对」的那种——它们错了游戏照样能玩，
只有在别人的机器上才炸，而那时你不在场。

所以这里不测「游戏能不能开」（那是 `testMain.py` 的事），只测环境检查那一段。
"""

import ast
import re
import sys
from pathlib import Path
from types import ModuleType

import run as runModule

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_PY = REPO_ROOT / "run.py"


def stubGame(monkeypatch, calls: list[int]) -> None:
    """把 `touhou.main` 换成假入口，这样测启动流程时不必真开窗口。

    **`touhou` 与 `touhou.main` 两级都要占住**：`from touhou.main import main`
    会先找 `touhou` 再找 `touhou.main`，只塞后面那个的话前者会被真的 import
    进来（测试环境里它有），然后真的去开窗口。
    """
    package = ModuleType("touhou")
    package.main = ModuleType("touhou.main")  # type: ignore[attr-defined]
    package.main.main = lambda: calls.append(1)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "touhou", package)
    monkeypatch.setitem(sys.modules, "touhou.main", package.main)  # type: ignore[attr-defined]


# —— 正常路径 ——


def testTheRealCheckoutLooksRunnable():
    """眼前这个仓库是完好的：三项检查全过，`environmentComplaint()` 返回 None。"""
    assert runModule.REPO_ROOT == REPO_ROOT
    assert runModule.environmentComplaint() is None


def testPathsComeFromThisFileNotFromTheWorkingDirectory(monkeypatch, tmp_path):
    """三个路径都由 `__file__` 推出来，**与当前工作目录无关**。

    这不是理论问题：从别的目录用绝对路径调用 `python D:/.../run.py` 是很常见的
    用法（桌面快捷方式、批处理文件都这么干），而如果路径取的是 `Path(".")`，
    那种调用方式会去找**调用者**目录下的 `src/`，然后报「找不到源码」。
    """
    monkeypatch.chdir(tmp_path)

    assert runModule.REPO_ROOT == REPO_ROOT
    assert runModule.SRC_DIR == REPO_ROOT / "src"
    assert runModule.ASSETS_DIR == REPO_ROOT / "assets"


def testRepoRootIsAbsoluteAndResolved():
    """路径要归一化过：`python run.py` 传的是相对路径，`resolve()` 让它变绝对。"""
    assert runModule.REPO_ROOT.is_absolute()
    assert runModule.REPO_ROOT.is_dir()


# —— 报错：三个坑各报一次，且要说人话 ——


def testPythonTooOldSaysBothVersionsAndTheInterpreter(monkeypatch):
    """版本不够时报出**要求的**与**当前的**，还要指出当前解释器是谁。

    一台机器上常有多个 Python。只说「版本太低」的话，玩家会去升级他以为的那个，
    而报错的其实是另一个。
    """
    monkeypatch.setattr(runModule, "MINIMUM_PYTHON", (99, 0))

    complaint = runModule.environmentComplaint()

    assert complaint is not None
    assert "99.0" in complaint, "要报出要求的版本"
    assert ".".join(str(part) for part in sys.version_info[:3]) in complaint, "也要报出当前版本"
    assert sys.executable in complaint, "还要指出这个解释器在哪"


def testMissingSourceComplainsAboutSource(monkeypatch, tmp_path):
    monkeypatch.setattr(runModule, "SRC_DIR", tmp_path / "没有这个目录")

    complaint = runModule.environmentComplaint()

    assert complaint is not None
    assert "源码目录" in complaint


def testMissingAssetsComplainsAboutAssets(monkeypatch, tmp_path):
    monkeypatch.setattr(runModule, "ASSETS_DIR", tmp_path / "没有这个目录")

    complaint = runModule.environmentComplaint()

    assert complaint is not None
    assert "素材目录" in complaint


def testMissingPygameTellsYouWhatToInstall(monkeypatch):
    monkeypatch.setattr(runModule, "_hasModule", lambda name: False)

    complaint = runModule.environmentComplaint()

    assert complaint is not None
    assert "pip install" in complaint
    assert "requirements.txt" in complaint


def testTheComplaintIsTheFirstOneNotAllOfThem(monkeypatch, tmp_path):
    """一次只报第一条不满足的。

    三件事一起坏时报八条，玩家会去修屏幕上最后那条，而第一句通常才是解法。
    """
    monkeypatch.setattr(runModule, "SRC_DIR", tmp_path / "没有这个目录")
    monkeypatch.setattr(runModule, "ASSETS_DIR", tmp_path / "也没有这个目录")
    monkeypatch.setattr(runModule, "_hasModule", lambda name: False)

    complaint = runModule.environmentComplaint()

    assert complaint is not None
    assert "源码目录" in complaint, "报的是源码那条（检查顺序里的第一条）"
    assert "素材目录" not in complaint, "后面几条不该跟着一起出来"


# —— 不写死路径 ——


def testNoAbsolutePathIsHardcoded():
    """`run.py` 里**一个写死的绝对路径都不许有**。

    这是它存在的理由：脚本要能被原样拷到任何机器、任何目录下运行。写死一个
    `D:\\...` 之后，它在写它的那台机器上照样能跑，所以谁也不会发现——直到
    别人拿到手。

    只扫字符串常量：判据是**字面量本身**长不长得像一个绝对位置（盘符、开头的
    `/`、`~`、UNC 的 `\\\\`）。拼出来的路径当然也在字符串里，但那些来自
    `__file__`，不是写死的。
    """
    tree = ast.parse(RUN_PY.read_text(encoding="utf-8"))
    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]

    absoluteLike = re.compile(r"^(?:[A-Za-z]:[\\/]|/|~[\\/]|\\\\)")
    offenders = [text for text in literals if absoluteLike.match(text)]

    assert offenders == [], f"这些字符串常量长得像绝对路径：{offenders}"


def testTheInstallHintIsARelativeCommand(monkeypatch):
    """缺依赖时给的那条命令必须是**相对路径**的。

    那句话的主要用途是被人抄走。绝对路径能在这台机器上跑通、抄到别人机器上就
    不行——而它看起来完全正常，所以没人会怀疑。
    """
    monkeypatch.setattr(runModule, "_hasModule", lambda name: False)

    complaint = runModule.environmentComplaint()

    assert complaint is not None
    assert "python -m pip install -r requirements.txt" in complaint
    assert str(REPO_ROOT) not in complaint


def testMinimumPythonMatchesPyproject():
    """`run.py` 的最低版本与 `pyproject.toml` 的 `requires-python` 必须一致。

    两处写给不同的人看：那个给 pip 看（决定装不装得上），这个给玩家看（决定报
    不报错）。改了一边忘了另一边，症状是「pip 说能装，run.py 说不能」或者反过来
    ——两种都很难让人联想到是两份声明不一致。
    """
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'requires-python\s*=\s*">=\s*(\d+)\.(\d+)"', text)

    assert match is not None, "pyproject.toml 里没找到 requires-python"
    assert (int(match.group(1)), int(match.group(2))) == runModule.MINIMUM_PYTHON


# —— 启动那一步 ——


def testMainReturnsOneAndPrintsTheComplaintToStderr(monkeypatch, capsys):
    """环境不行时 `main()` 返回 1，并且把原因打在 **stderr** 上。

    打 stderr 而不是 stdout：这条消息是给「启动失败」用的，混进正常输出里会让
    管道、重定向、日志都分不清哪一行算错误。
    """
    monkeypatch.setattr(runModule, "ASSETS_DIR", Path("不存在的目录"))

    assert runModule.main() == 1

    captured = capsys.readouterr()
    assert "素材目录" in captured.err
    assert captured.out == ""


def testMainInsertsSrcAndLaunchesTheGame(monkeypatch):
    """环境没问题时，`main()` 把 `src/` 挂进 `sys.path` 再调游戏入口。

    这条同时钉住「**不装包**」：`touhou` 必须是从 `src/` import 到的。开发机上
    这条断言容易假绿——有人跑过 `pip install -e .` 之后，site-packages 里也有
    一份，于是「免安装」这个卖点在唯一会测试它的机器上恰好测不出来。
    """
    calls: list[int] = []
    stubGame(monkeypatch, calls)
    monkeypatch.setattr(runModule.sys, "path", ["/别处"])

    assert runModule.main() == 0

    assert calls == [1], "游戏入口该被调用一次"
    assert sys.path[0] == str(runModule.SRC_DIR), "src/ 要插在**最前面**"


def testHasModuleSeesAnInstalledDependency():
    """`_hasModule` 对真的装了的包返回 True（否则整条检查形同虚设）。"""
    assert runModule._hasModule("pygame")
    assert not runModule._hasModule("绝对不存在的包名")
