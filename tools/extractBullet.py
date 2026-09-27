"""从 `gather.png` 那类「一堆弹挤在一张黑底图上」的素材里抠出单独一颗弹。

`assets/sprites/projectiles_and_items/gather.png` 是一张参考图：上百颗弹压在**不透明
的黑底**上、彼此挨得很近，而且大玉中间还画着**判定圈**（原作给玩家的辅助线，
我们用不上——判定半径是我们自己按 `hitboxRadius` 设的）。

这个工具做三件事：

1. **黑底转透明**：从图的四边洪水填充近黑像素。不能按「像素是黑的就透明」来，
   弹体本身也有很暗的地方（深蓝的核心）——只有**和边连通**的黑才是背景。
2. **只留目标那一颗**：裁剪难免切到邻弹，那些碎片是另一个连通块，丢掉。
   留下的那一块（含辉光）是唯一的。
3. **抹掉判定圈**：判定圈恰好画在球缘那 2px 上（实测 navy 到 r=33、亮线在 35~36、
   光环从 37 起），用球内的颜色替掉即可。**只换这两三像素，不外扩**——整段都换的话
   球会胖一圈，跟原作者画的大小对不上。

用法：

    python tools/extractBullet.py                     # 默认抠蓝色大玉（写进 assets/）
    python tools/extractBullet.py <图> <输出> <x> <y> <缩放>   # 抠别的：坐标 + 缩放

**球心坐标**是唯一要人工给的东西：它在图上量得出来（找那一片深蓝的连通块的中点）。
球半径不用给，工具自己量——但**判定圈的颜色判据（`isBall`）是按深蓝球写的**，
换成别的颜色（比如红色大玉的球心是深红）要改那一个函数。

输出贴图**以球心为中心**、四边对称：`Bullet` 是按中心画的，偏一个像素都不行。
"""

from __future__ import annotations

import collections
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SHEET = PROJECT_ROOT / "assets" / "sprites" / "projectiles_and_items" / "gather.png"
DEFAULT_OUT = (
    PROJECT_ROOT / "assets" / "sprites" / "projectiles_and_items" / "big_bullet_blue_0.png"
)
DEFAULT_CENTER = (683.0, 947.0)  # 蓝色大玉的球心（图中量得）
# 输出缩放：素材图上的大玉是 172px（原作的尺寸），在 384×448 的游戏区里占 45% 宽，
# 太大。缩到 0.45 → 贴图 77px、球体 33px，是常见大玉的量级。
# **要改大小就改这里、从原图重抠**：在已经缩过的图上再缩一次会多丢一道细节。
# **判定半径要跟着一起缩**（见关卡数据）：缩小贴图却留着原来的判定，会做出
# 「判定圈比看得见的球还大」的子弹——那是最招人骂的一类判定。
DEFAULT_SCALE = 0.45

# 裁剪余量：够大到让目标那颗弹完全不碰边，邻弹的碎片才好认出来丢掉
PAD = 100
# 判定圈在球缘两侧各取这么多像素替换掉
RING_HALF_WIDTH = 2
# 光晕的 alpha 羽化：亮度 ≤ LOW 全透明、≥ HIGH 全不透明，中间线性
ALPHA_LOW = 40
ALPHA_HIGH = 120
# 「背景」判据：三通道之和
NEAR_BLACK = 45
# 判定圈的半径扫描范围（球心向外找第一次连续这么多个近黑像素）
DARK_RUN = 6


def isNearBlack(color: tuple[int, int, int]) -> bool:
    return sum(color) < NEAR_BLACK


def isBall(color: tuple[int, int, int]) -> bool:
    """深蓝球体的判据。

    **按颜色写死是有意的**：球心与光环、辉光靠色相区分（深蓝的绿通道 ≈26，
    紫光环的绿通道 ≈0），比「靠亮度」可靠得多——光环比球还亮。
    抠别的颜色的弹时改这里。
    """
    return 12 < color[1] < 70 and color[0] < 60 and 70 < color[2] < 220


def extract(sheetPath: Path, outPath: Path, center: tuple[float, float], scale: float = 1.0) -> str:
    import pygame

    sheet = pygame.image.load(str(sheetPath))
    cx, cy = center

    # —— 量球心周围的球体半径 ——
    xs: list[int] = []
    ys: list[int] = []
    for y in range(int(cy) - 70, int(cy) + 70):
        for x in range(int(cx) - 70, int(cx) + 70):
            if isBall(tuple(sheet.get_at((x, y)))[:3]):
                xs.append(x)
                ys.append(y)
    if not xs:
        raise SystemExit(f"({cx}, {cy}) 附近没找到球体——颜色判据 isBall 要改")
    ballRadius = ((max(xs) - min(xs)) + (max(ys) - min(ys))) / 4

    # —— 裁一块，四边洪水填充背景 ——
    box = pygame.Rect(int(cx) - PAD, int(cy) - PAD, PAD * 2, PAD * 2)
    crop = sheet.subsurface(box).copy().convert_alpha()
    width, height = crop.get_size()
    middle = (width / 2, height / 2)

    background = [[False] * width for _ in range(height)]
    queue: collections.deque[tuple[int, int]] = collections.deque()
    for x in range(width):
        queue.append((x, 0))
        queue.append((x, height - 1))
    for y in range(height):
        queue.append((0, y))
        queue.append((width - 1, y))
    while queue:
        x, y = queue.popleft()
        if background[y][x] or not isNearBlack(tuple(crop.get_at((x, y)))[:3]):
            continue
        background[y][x] = True
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if 0 <= x + dx < width and 0 <= y + dy < height:
                queue.append((x + dx, y + dy))

    # —— 只留球心所在的那一坨（邻弹碎片是另一坨）——
    keep = [[False] * width for _ in range(height)]
    queue = collections.deque([(int(middle[0]), int(middle[1]))])
    while queue:
        x, y = queue.popleft()
        if keep[y][x] or background[y][x]:
            continue
        keep[y][x] = True
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if 0 <= x + dx < width and 0 <= y + dy < height:
                queue.append((x + dx, y + dy))

    # —— 抹判定圈：沿每条射线，把球缘那一圈换成球内的颜色 ——
    for step in range(2880):
        angle = 2 * math.pi * step / 2880
        ux, uy = math.cos(angle), math.sin(angle)
        sample = tuple(
            crop.get_at(
                (int(middle[0] + ux * (ballRadius - 7)), int(middle[1] + uy * (ballRadius - 7)))
            )
        )[:3]
        for r in range(int(ballRadius - RING_HALF_WIDTH), int(ballRadius + RING_HALF_WIDTH + 1)):
            x, y = int(middle[0] + ux * r), int(middle[1] + uy * r)
            if keep[y][x]:
                crop.set_at((x, y), sample)

    # —— 贴内容裁紧，**但四边对称**：球心必须落在贴图正中 ——
    inks = [(x, y) for y in range(height) for x in range(width) if keep[y][x]]
    reach = (
        int(
            max(
                middle[0] - min(x for x, _ in inks),
                max(x for x, _ in inks) - middle[0],
                middle[1] - min(y for _, y in inks),
                max(y for _, y in inks) - middle[1],
            )
        )
        + 1
    )
    size = reach * 2
    out = pygame.Surface((size, size), pygame.SRCALPHA)
    for y in range(size):
        for x in range(size):
            sx, sy = int(middle[0] - reach + x), int(middle[1] - reach + y)
            if not (0 <= sx < width and 0 <= sy < height) or not keep[sy][sx]:
                continue
            color = tuple(crop.get_at((sx, sy)))[:3]
            if isBall(color):
                alpha = 255  # 球体一律不透明
            else:
                level = max(color)
                alpha = (
                    0
                    if level <= ALPHA_LOW
                    else (255 if level >= ALPHA_HIGH else round(255 * (level - ALPHA_LOW) / 80))
                )
            out.set_at((x, y), (*color, alpha))

    if scale != 1.0:
        # 用 smoothscale：这张图是柔和的光晕，不是硬边像素画，最近邻会起锯齿
        size = max(1, round(size * scale))
        out = pygame.transform.smoothscale(out, (size, size))

    pygame.image.save(out, str(outPath))
    return (
        f"输出 {outPath.name}：{size}×{size}（缩放 {scale}×），弹心在正中；"
        f"球直径 {2 * ballRadius * scale:.0f}（球半径 {ballRadius * scale:.1f}）——"
        f"判定半径按同一比例缩：原来的判定 × {scale} 就是新的"
    )


def main(argv: list[str]) -> int:
    import os

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame

    pygame.init()
    pygame.display.set_mode((1, 1))

    sheetPath = Path(argv[0]) if argv else DEFAULT_SHEET
    outPath = Path(argv[1]) if len(argv) > 1 else DEFAULT_OUT
    center = (float(argv[2]), float(argv[3])) if len(argv) > 3 else DEFAULT_CENTER
    scale = float(argv[4]) if len(argv) > 4 else DEFAULT_SCALE

    print(extract(sheetPath, outPath, center, scale))
    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
