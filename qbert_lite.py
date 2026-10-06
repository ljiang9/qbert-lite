#!/usr/bin/env python3
"""qbert-lite：极简 Q*bert 克隆 —— 跳格子变色、躲敌人、乘碟子逃生。

纯标准库。交互为回合制（每行一个命令），另提供 --auto 无头演示。
"""

import argparse
import random
import sys

ROWS = 7                 # 金字塔行数（0..6）
STAGES = 3               # 方块颜色阶段数，目标是全部变为 STAGES-1
SCORE_HOP = 25           # 跳到方块改变颜色得分
SCORE_COILY_KILL = 500   # 用碟子杀掉 Coily
SCORE_DISC = 100         # 乘碟子逃生
SCORE_BALL_AVOID = 100   # 红球掉到金字塔外
FREEZE_TICKS = 10        # 绿球冻结敌人步数

STAGE_GLYPH = {0: "·", 1: "◍", 2: "●"}

# 四个跳向：(dr, dc)
MOVES = {
    "ul": (-1, -1),  # 左上
    "ur": (-1, 0),   # 右上
    "dl": (1, 0),    # 左下
    "dr": (1, 1),    # 右下
}


def valid(r, c):
    return 0 <= r < ROWS and 0 <= c <= r


class Enemy:
    def __init__(self, kind, r, c):
        self.kind = kind          # "coily" "slick" "red" "green"
        self.r, self.c = r, c
        self.active = True

    def __repr__(self):
        return f"<{self.kind}@({self.r},{self.c})>"


class Game:
    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.cubes = [[0 for _ in range(r + 1)] for r in range(ROWS)]
        self.pr, self.pc = 0, 0
        self.lives = 3
        self.score = 0
        self.over = False
        self.win = False
        self.ticks = 0
        self.enemies = []
        self.discs = {(2, 0): "ul", (4, 4): "ur"}  # (r,c) -> 触发碟子的跳向
        self.freeze = 0
        self.coily_killed = 0
        self._died_this_hop = False

    # ---------- 内部 ----------
    def _land(self):
        """玩家落在 (pr,pc) 上的效果。"""
        stage = self.cubes[self.pr][self.pc]
        if stage < STAGES - 1:
            self.cubes[self.pr][self.pc] = stage + 1
            self.score += SCORE_HOP
        for e in self.enemies:
            if self._died_this_hop:
                break
            if e.active and (e.r, e.c) == (self.pr, self.pc):
                if e.kind == "green":
                    e.active = False
                    self.freeze = FREEZE_TICKS
                    self.score += 50
                else:
                    self._die()
                    return
        if all(c == STAGES - 1 for row in self.cubes for c in row):
            self.win = True
            self.over = True

    def _die(self):
        if self._died_this_hop:
            return
        self._died_this_hop = True
        self.lives -= 1
        if self.lives <= 0:
            self.over = True
        else:
            self.pr, self.pc = 0, 0
            self.cubes[0][0] = min(STAGES - 1, self.cubes[0][0] + 1)

    def spawn_wave(self):
        """按玩家步数逐渐放出敌人。"""
        if (self.pr, self.pc) == (0, 0):
            return  # 玩家复活点不刷怪，避免出生杀
        kinds = ["slick"]
        if self.ticks >= 4:
            kinds.append("red")
        if self.ticks >= 8:
            kinds.append("coily")
        if self.ticks >= 12:
            kinds.append("green")
        live_kinds = {e.kind for e in self.enemies if e.active}
        for k in kinds:
            if k not in live_kinds and self.rng.random() < 0.25:
                self.enemies.append(Enemy(k, 0, 0))
                break

    def _enemy_step(self, e):
        if self.freeze > 0:
            return
        if e.kind == "coily":
            opts = []
            for mv, (dr, dc) in MOVES.items():
                nr, nc = e.r + dr, e.c + dc
                if valid(nr, nc):
                    opts.append((nr, nc))
            if not opts:
                return
            # 追逐玩家：选曼哈顿距离最小的
            opts.sort(key=lambda p: abs(p[0] - self.pr) + abs(p[1] - self.pc))
            e.r, e.c = opts[0]
        elif e.kind == "slick":
            opts = [(e.r + dr, e.c + dc) for dr, dc in MOVES.values()]
            opts = [(nr, nc) for nr, nc in opts if valid(nr, nc)]
            if opts:
                e.r, e.c = self.rng.choice(opts)
            self.cubes[e.r][e.c] = 0  # 恶作剧：把方块改回初始色
        elif e.kind in ("red", "green"):
            # 一直向下掉
            dr, dc = self.rng.choice([(1, 0), (1, 1)])
            nr, nc = e.r + dr, e.c + dc
            if valid(nr, nc):
                e.r, e.c = nr, nc
            else:
                e.active = False
                if e.kind == "red":
                    self.score += SCORE_BALL_AVOID
        if (e.r, e.c) == (self.pr, self.pc) and e.kind != "green":
            self._die()
        elif (e.r, e.c) == (self.pr, self.pc) and e.kind == "green":
            e.active = False
            self.freeze = FREEZE_TICKS
            self.score += 50

    # ---------- 玩家动作 ----------
    def hop(self, mv):
        """玩家跳一次。返回中文结果描述。"""
        if self.over or mv not in MOVES:
            return "无效"
        self._died_this_hop = False
        dr, dc = MOVES[mv]
        nr, nc = self.pr + dr, self.pc + dc
        # 碟子逃生：从特定位置跳向碟子
        if (self.pr, self.pc) in self.discs and self.discs[(self.pr, self.pc)] == mv:
            del self.discs[(self.pr, self.pc)]
            self.score += SCORE_DISC
            for e in self.enemies:
                if e.active and e.kind == "coily":
                    e.active = False
                    self.score += SCORE_COILY_KILL
                    self.coily_killed += 1
            self.pr, self.pc = 0, 0
            self.ticks += 1
            self._land()
            return "乘碟子逃回顶部！"
        if not valid(nr, nc):
            self._die()
            self.ticks += 1
            return "掉下金字塔！"
        self.pr, self.pc = nr, nc
        self.ticks += 1
        self.spawn_wave()
        if self.ticks % 2 == 0:
            for e in self.enemies:
                if e.active:
                    self._enemy_step(e)
        if self.freeze > 0:
            self.freeze -= 1
        self._land()
        if self.win:
            return "全部变色，胜利！"
        if self.over:
            return "游戏结束。"
        return "跳"

    # ---------- 渲染 ----------
    def render(self):
        lines = []
        for r in range(ROWS):
            pad = "  " * (ROWS - r - 1)
            cells = []
            for c in range(r + 1):
                ch = STAGE_GLYPH[self.cubes[r][c]]
                if (r, c) == (self.pr, self.pc):
                    ch = "Q"
                else:
                    for e in self.enemies:
                        if e.active and (e.r, e.c) == (r, c):
                            ch = {"coily": "C", "slick": "S",
                                  "red": "R", "green": "G"}[e.kind]
                cells.append(ch)
            disc_mark = ""
            if (r, 0) in self.discs:
                disc_mark += "◁"
            if (r, r) in self.discs:
                disc_mark += "▷"
            lines.append(pad + " ".join(cells) + ("  " + disc_mark if disc_mark else ""))
        return "\n".join(lines)

    def status(self):
        cubes_done = sum(1 for row in self.cubes for c in row if c == STAGES - 1)
        return (f"分数 {self.score} | 生命 {self.lives} | 已变色 {cubes_done}/{ROWS*(ROWS+1)//2} "
                f"| 敌人 {sum(1 for e in self.enemies if e.active)} | 步数 {self.ticks}")


def auto_play(seed=None, moves=200, verbose=False):
    """贪心 AI：跳向最近的未完成方块，避开敌人和跌落。"""
    g = Game(seed)
    dirs = list(MOVES)
    for _ in range(moves):
        if g.over:
            break
        best, best_key = None, None
        for mv in dirs:
            dr, dc = MOVES[mv]
            nr, nc = g.pr + dr, g.pc + dc
            if (g.pr, g.pc) in g.discs and g.discs[(g.pr, g.pc)] == mv:
                best, best_key = mv, (-10**9, 0)  # 有 Coily 就优先坐碟子
                break
            if not valid(nr, nc):
                continue
            if any(e.active and (e.r, e.c) == (nr, nc) and e.kind != "green"
                   for e in g.enemies):
                continue
            # 离最近未完成方块的距离（跳的方块若已完成则加惩罚）
            target = min(
                (abs(r - nr) + abs(c - nc)
                 for r in range(ROWS) for c in range(r + 1)
                 if g.cubes[r][c] < STAGES - 1),
                default=0,
            )
            done_pen = 0 if g.cubes[nr][nc] < STAGES - 1 else 5
            # 避开 Coily 附近（它追你）
            coily_near = any(
                e.active and e.kind == "coily"
                and abs(e.r - nr) + abs(e.c - nc) <= 1 for e in g.enemies)
            key = (target + done_pen + (3 if coily_near else 0), mv)
            if best_key is None or key < best_key:
                best, best_key = mv, key
        if best is None:  # 无安全跳，随便跳
            best = dirs[0]
        g.hop(best)
        if verbose and g.ticks % 20 == 0:
            print(g.render())
            print(g.status())
    return g


def main(argv=None):
    ap = argparse.ArgumentParser(description="qbert-lite：极简 Q*bert 克隆")
    ap.add_argument("--auto", action="store_true", help="无头自动演示")
    ap.add_argument("--moves", type=int, default=200, help="自动演示步数")
    ap.add_argument("--seed", type=int, default=None, help="随机种子")
    ap.add_argument("--verbose", action="store_true", help="自动演示时打印棋盘")
    args = ap.parse_args(argv)

    if args.auto:
        g = auto_play(seed=args.seed, moves=args.moves, verbose=args.verbose)
        print(g.render())
        print(g.status())
        print("结果:", "胜利！" if g.win else ("结束（生命耗尽）" if g.over else "步数用完"))
        return 0

    if not sys.stdin.isatty():
        print("交互模式需要终端；无头演示请用 --auto", file=sys.stderr)
        return 2
    g = Game(args.seed)
    print("操作: ul(左上) ur(右上) dl(左下) dr(右下)，碟子在第3行左侧◁/第5行右侧▷，q 退出")
    print("图例: Q=你 C=Coily(追你) S=Slick(改回颜色) R=红球(躲) G=绿球(冻敌人)")
    while not g.over:
        print(g.render())
        print(g.status())
        try:
            cmd = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if cmd == "q":
            break
        print(g.hop(cmd))
    print("胜利！" if g.win else "游戏结束", f"得分 {g.score}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
