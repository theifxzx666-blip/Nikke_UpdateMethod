# -*- coding: utf-8 -*-
r"""runlib.py — Skill 编排引擎（各 Skill 的 run.py 共用这一个模块）

为什么要有它
------------
每个 Skill 的 SKILL.md 里都有一串「先跑 A 再跑 B」的步骤。靠人按文档手敲有三类问题：
  ① 顺序靠记，漏一步不报错（例如 03 忘了导完先自检 ratio，直接拿病态网格去渲）
  ② 参数散在正文里，容易传到上一期的目录
  ③ 跑没跑过、跑到哪，全靠回忆

本模块只做三件事：**把步骤写成表、把状态从产物反推、把命令按 UTF-8 跑起来**。

四条硬规则（写 run.py 时不许违）
--------------------------------
1. **只信产物**：`done` 由「产物存在 + 非空 + 判据通过」推出，不看有没有跑过。
   没有任何状态文件、没有 `.done` 标记 —— 删产物就是重跑，不需要清理任何记录。
2. **手动步骤标 MANUAL**：写死常量、需人改参数、需人眼看图的，一律 `manual=`，
   看板明确标 `MAN!`，`--run` 不会假装能自动。
3. **子进程强制 UTF-8**：`PYTHONIOENCODING=utf-8` + `PYTHONUTF8=1`。
   Windows 中文控制台默认 GBK，UnityPy/json 里的中文会直接 UnicodeEncodeError。
4. **路径只用占位符**：步骤表里不写 `D:\Codex\...`，一律 `{WORK}` / `{OUT}` 之类，
   由环境变量解析。换机器、换期号只改环境变量，不改代码。

占位符
------
  {PY}       解释器（默认取 NIKKE_PY，退到当前进程的 sys.executable）
  {SCRIPTS}  本 Skill 的 scripts 目录
  {SKILL}    本 Skill 根目录
  {WORK}     NIKKE_WORK    当期工作区（拉包 / 解密产物落地处）
  {OUT}      NIKKE_OUT     当期交付目录，默认 {WORK}\out
  {STATIC}   NIKKE_STATIC  mpdump 输出的静态表目录
  {REPO}     NIKKE_REPO    拆包资源库根
  {ROOT}     NIKKE_ROOT    版本更新根

用法（在 run.py 里）
--------------------
    from runlib import Step, Board, main

    STEPS = [
        Step("01", "认包统计", cmd=("{PY}", "{SCRIPTS}/stat.py", "{WORK}/a.bundle"),
             outs=("{OUT}/stat.json",)),
        Step("02", "改常量", manual="改 build_voice_pack.py 顶部 c870/c871/c872",
             outs=("{OUT}/voice/*.mp3",)),
    ]

    if __name__ == "__main__":
        raise SystemExit(main(Board("03-asset-extract", STEPS)))

命令行
------
  python run.py --status              # 看板（默认）
  python run.py --status --all        # 连通过和未通过的都列全（默认就全列）
  python run.py --run 02              # 跑一步
  python run.py --run all             # 按顺序跑所有 pending，遇错停
  python run.py --run all --dry       # 只打印要跑什么，不动手
  python run.py --json                # 机器可读状态

退出码
------
  0 = 全部 DONE（manual 不算未完成）
  1 = 还有 PENDING / BLOCKED
  2 = 用法错误 / 跑到一半失败
"""

from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------- 状态与显示

DONE, PEND, MANU, BLOK = "DONE", "PEND", "MAN!", "BLOK"

TAG = {DONE: "[DONE]", PEND: "[PEND]", MANU: "[MAN!]", BLOK: "[BLOK]"}


def dw(s: str) -> int:
    """显示宽度。中日韩全角按 2 算，表格才不会错位。"""
    w = 0
    for ch in s:
        w += 2 if (u"\u1100" <= ch <= u"\u115f" or u"\u2e80" <= ch <= u"\ua4cf"
                   or u"\uac00" <= ch <= u"\ud7a3" or u"\uf900" <= ch <= u"\ufaff"
                   or u"\ufe30" <= ch <= u"\ufe6f" or u"\uff00" <= ch <= u"\uff60"
                   or u"\uffe0" <= ch <= u"\uffe6") else 1
    return w


def pad(s: str, n: int) -> str:
    """按显示宽度左对齐补空格（超长不截断，宁可错位也不丢信息）。"""
    return s + " " * max(0, n - dw(s))


# ---------------------------------------------------------------- 占位符解析

def env_paths(skill_dir: Path, extra: dict | None = None) -> dict:
    """收集占位符实际值。缺的变量给空串，由 resolve 时报错，不静默猜路径。

    `extra` 用于 Skill 自己的选料变量（如 03 的 {MODEL}），格式 {占位符: 环境变量名}。
    """
    work = os.environ.get("NIKKE_WORK", "")
    out = os.environ.get("NIKKE_OUT", "") or (str(Path(work) / "out") if work else "")
    env = {
        "PY": os.environ.get("NIKKE_PY", "") or sys.executable,
        "SCRIPTS": str(skill_dir / "scripts"),
        "SKILL": str(skill_dir),
        "WORK": work,
        "OUT": out,
        "STATIC": os.environ.get("NIKKE_STATIC", ""),
        "REPO": os.environ.get("NIKKE_REPO", ""),
        "ROOT": os.environ.get("NIKKE_ROOT", ""),
    }
    for key, var in (extra or {}).items():
        env[key] = os.environ.get(var, "")
    return env


def resolve(tmpl: str, env: dict) -> str:
    """把 {WORK} 之类换掉。占位符没配值就抛错 —— 不许把 '{WORK}' 当路径用。

    占位符与变量名一一对应（{MODEL} ↔ NIKKE_MODEL），报错时直接点名要设哪个变量。
    """
    out = tmpl
    for k, v in env.items():
        tok = "{" + k + "}"
        if tok not in out:
            continue
        if not v:
            raise KeyError(f"未设 NIKKE_{k}（占位符 {tok}）")
        out = out.replace(tok, v)
    # 统一分隔符：环境变量常从 bash 里带正斜杠，路径混着写出来难读
    return os.path.normpath(os.path.expandvars(os.path.expanduser(out)))


# ---------------------------------------------------------------- 步骤定义

@dataclass
class Step:
    """一个步骤。产物判定优先于一切 —— 没有产物就是没做完。"""

    sid: str                      # 编号，如 "01"
    title: str                    # 一句话标题
    cmd: tuple = ()               # 命令模板；空元组 + manual 非空 = 纯手动
    outs: tuple = ()              # 产物（支持 glob）；全部命中才算 DONE
    needs: tuple = ()             # 前置产物；缺了标 BLOK
    pred: str = ""                # 判据的人话说明，看板「备注」列用
    check: object = None          # 额外判据：fn(list[Path]) -> (bool, str)
    manual: str = ""              # 非空 = 手动步骤，值是「怎么做」
    note: str = ""
    tags: tuple = field(default=())

    def __post_init__(self):
        self.cmd = tuple(self.cmd)
        self.outs = tuple(self.outs)
        self.needs = tuple(self.needs)


def _expand_globs(patterns, env, allow_dir: bool = False) -> tuple:
    r"""展开产物模式。返回 (命中文件列表, 未命中的模式列表)。

    allow_dir=True 用于 needs —— 前置可以是一个目录（例如 device\ 整包）；
    outs 一律要求是文件，空目录不算有产物。
    """
    hit, miss = [], []
    for pat in patterns:
        # 以斜杠结尾表示「这是个目录产物」，且要求目录里至少有一个文件
        # （空目录不算有产物 —— 否则 mkdir 一下就算做完了）
        want_dir = pat.endswith(("/", "\\"))
        p = Path(resolve(pat.rstrip("/\\"), env))
        if want_dir:
            if p.is_dir() and any(x.is_file() for x in p.rglob("*")):
                hit.append(p)
            else:
                miss.append(pat)
            continue
        # 带通配的走 glob，不带通配的直接判存在（省一次目录扫描）
        if any(ch in str(p) for ch in "*?["):
            got = [x for x in p.parent.glob(p.name) if x.is_file() and x.stat().st_size > 0]
            if got:
                hit.extend(got)
            else:
                miss.append(pat)
        else:
            ok = p.is_file() and p.stat().st_size > 0
            if allow_dir and p.is_dir():
                ok = True
            if ok:
                hit.append(p)
            else:
                miss.append(pat)
    return hit, miss


def step_state(st: Step, env: dict) -> tuple:
    """推出单步状态。返回 (状态, 说明)。

    判据顺序：manual 先判（手动步骤没法自动验完成，靠 outs 兜底），
    然后 needs 缺失 → BLOK，然后 outs 全中 → DONE，否则 PEND。
    """
    try:
        n_hit, n_miss = _expand_globs(st.needs, env, allow_dir=True)
    except KeyError as e:
        return BLOK, str(e.args[0] if e.args else e)
    if n_miss:
        return BLOK, "缺输入: " + ", ".join(n_miss)

    if st.manual:
        # 手动步骤：产物齐了就算做完，没齐就看板提示「要人做」
        if st.outs:
            try:
                _, miss = _expand_globs(st.outs, env)
            except KeyError:
                return MANU, st.manual
            if not miss:
                return DONE, st.manual
        return MANU, st.manual

    if not st.outs:
        # 没有产物就没法判定 —— 不许让「跑过就算完成」蒙混过去
        return BLOK, "步骤表未声明产物，无法判定（补 outs 或改 manual）"

    try:
        hit, miss = _expand_globs(st.outs, env)
    except KeyError as e:
        return BLOK, str(e.args[0] if e.args else e)

    if miss:
        return PEND, "缺产物: " + ", ".join(miss)

    if st.check:
        try:
            ok, why = st.check(hit)
        except Exception as e:                     # 判据自己炸了不算通过
            return PEND, f"判据异常: {e}"
        if not ok:
            return PEND, why
        return DONE, why or st.pred
    return DONE, st.pred


# ---------------------------------------------------------------- 判据小工具

def pred_json_min(key: str, minimum: float, what: str = ""):
    """读产物 JSON 的某个数值键，要求 >= minimum。用来卡 ratio / 三角面数。"""

    def _chk(files):
        for f in files:
            if f.suffix.lower() != ".json":
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                continue
            val = data
            for part in key.split("."):
                if isinstance(val, dict) and part in val:
                    val = val[part]
                else:
                    val = None
                    break
            if isinstance(val, (int, float)):
                label = what or key
                return (val >= minimum,
                        f"{label}={val:g}（门限 {minimum:g}）")
        return False, f"产物里找不到 {key}"

    return _chk


def pred_min_count(suffix: str, n: int):
    """命中产物里某后缀的文件数 >= n（例如「至少 3 个 gif」）。"""
    def _chk(files):
        cnt = sum(1 for f in files if f.suffix.lower() == suffix.lower())
        return cnt >= n, f"{suffix} 共 {cnt} 个（需 {n}）"
    return _chk


# ---------------------------------------------------------------- 看板

class Board:
    def __init__(self, name: str, steps, note: str = "", extra: dict | None = None):
        self.name = name
        self.steps = list(steps)
        self.note = note
        self.extra = extra or {}
        self.skill_dir = self._guess_skill_dir()
        self.env = env_paths(self.skill_dir, self.extra)

    def _guess_skill_dir(self) -> Path:
        """run.py 在 scripts/ 下，往上两级就是 Skill 根。"""
        p = Path(sys.argv[0]).resolve()
        return p.parent.parent if p.parent.name == "scripts" else p.parent

    def snapshot(self):
        """[(step, state, why)] —— 一次算全，后面所有命令都用这一份。"""
        return [(st,) + step_state(st, self.env) for st in self.steps]

    # ---- 输出

    def show(self, as_json: bool = False) -> int:
        snap = self.snapshot()
        if as_json:
            print(json.dumps({
                "skill": self.name,
                "env": self.env,
                "steps": [{"id": st.sid, "title": st.title, "state": s, "why": w}
                          for st, s, w in snap],
            }, ensure_ascii=False, indent=2))
            return 0 if all(s in (DONE, MANU) for _, s, _ in snap) else 1

        print(f"\n{self.name}   共 {len(snap)} 步")
        if self.note:
            print(f"  {self.note}")
        print(f"  WORK   = {self.env['WORK'] or '（未设置 NIKKE_WORK）'}")
        print(f"  OUT    = {self.env['OUT'] or '（未设置）'}")
        print(f"  PY     = {self.env['PY']}")
        print()

        # 步骤列宽按最长标题自适应（封顶 42，否则一条长标题会把整张表推开）
        wstep = max([20] + [min(42, dw(st.title)) for st in self.steps])
        bar = "  " + "-" * (3 + 2 + 7 + 2 + wstep + 2 + 58)
        print("  " + "  ".join((pad("#", 3), pad("状态", 7), pad("步骤", wstep), "判据 / 备注")))
        print(bar)
        detail = []
        for st, s, w in snap:
            why = w.replace("\n", " ")
            if s == MANU:
                # 手动步骤的做法太长，塞进表格会挤掉别的列 —— 只在表里点一下，
                # 真正的命令放到表下「补充说明」，方便照着复制
                why = "需人工（见下）"
                detail.append((st, w))
            elif dw(why) > 58:
                # 产物路径的尾巴是有信息量的（*.glb / *_立绘.png），不能中段截断
                why_head = why.split(":")[0] if ":" in why else why[:20]
                detail.append((st, w))
                why = why_head + "（见下）"
            print("  " + "  ".join((pad(st.sid, 3), pad(TAG[s], 7), pad(st.title, wstep), why)))

        cnt = {}
        for _, s, _ in snap:
            cnt[s] = cnt.get(s, 0) + 1
        line = "  ".join(f"{TAG[k]} {v}" for k, v in
                         ((DONE, cnt.get(DONE, 0)), (PEND, cnt.get(PEND, 0)),
                          (MANU, cnt.get(MANU, 0)), (BLOK, cnt.get(BLOK, 0))))
        print(bar)
        print("  合计: " + line)

        if detail:
            print("\n  补充说明（手动步骤的做法 / 没满足的产物清单）")
            for st, w in detail:
                print(f"    [{st.sid}] {st.title}")
                for ln in w.splitlines() or [""]:
                    print(f"         {ln}")
        left = [st.sid for st, s, _ in snap if s in (PEND, BLOK)]
        if left:
            print(f"  下一步: --run {left[0]}    全跑: --run all")
        else:
            print("  全部产物齐备。")
        print()
        return 0 if all(s in (DONE, MANU) for _, s, _ in snap) else 1

    # ---- 执行

    def run_one(self, st: Step, dry: bool, verbose: bool = True) -> bool:
        """跑一步。返回是否成功（manual / 已成 / 跑通都算 True）。"""
        state, why = step_state(st, self.env)

        if st.manual:
            print(f"\n[{st.sid}] {st.title}  —— 手动步骤")
            print(f"  做法: {st.manual}")
            if state == DONE:
                print("  产物已齐，无需再做。")
                return True
            if st.outs:
                print("  产物未齐: " + ", ".join(st.outs))
            # 手动步骤不假装能自动，也不挡住 --run all：跳过并把做法留在屏上，
            # 下游若真依赖它的产物，会由 needs 判 BLOK 拦住。
            print("  → 跳过，请人工执行上面这条命令。")
            return True

        if state == DONE:
            print(f"\n[{st.sid}] {st.title}  —— 产物已齐，跳过")
            return True
        if state == BLOK:
            # dry 模式下前置产物当然还没生成（前面的步骤没真跑），
            # 这时把命令打出来并标明会停，才看得出整条链要跑什么
            if dry and st.cmd:
                print(f"\n[{st.sid}] {st.title}  —— 前置未满足: {why}")
                print("  $ " + " ".join(_expand_argv([resolve(x, self.env) for x in st.cmd])))
                print("  （实际执行会停在这一步，先把上面的步骤跑完）")
                return True
            print(f"\n[{st.sid}] {st.title}  —— 前置不满足: {why}")
            return False
        if not st.cmd:
            print(f"\n[{st.sid}] {st.title}  —— 没有命令模板，也没有 manual 说明"
                  f"（步骤表写错了）")
            return False

        argv = [resolve(x, self.env) for x in st.cmd]
        argv = _expand_argv(argv)
        if verbose:
            print(f"\n[{st.sid}] {st.title}")
            print("  $ " + " ".join(argv))
        if dry:
            return True

        _ensure_dirs(st.outs, self.env)
        ok = _spawn(argv, self.skill_dir)
        if not ok:
            print(f"  [FAIL] 退出码非 0，停在 {st.sid}")
            return False

        # 产物判定重算一次 —— 脚本返回 0 但没产出文件，照样算失败
        state2, why2 = step_state(st, self.env)
        if state2 != DONE:
            print(f"  [FAIL] 命令成功但产物不合判据: {why2}")
            print("         不往下游走 —— 下游会拿半成品继续，错到最后一页才发现。")
            return False
        if verbose:
            print(f"  [ OK ] {why2 or state2}")
        return True

    def run(self, target: str, dry: bool) -> int:
        if target == "all":
            todo = self.steps
        else:
            todo = [st for st in self.steps if st.sid == target or st.title == target]
            if not todo:
                ids = ", ".join(st.sid for st in self.steps)
                print(f"没有这一步: {target}（可选 {ids}）")
                return 2
        for st in todo:
            if not self.run_one(st, dry):
                return 1
        if dry:
            print("\n--dry 结束，没有执行任何命令。")
        return 0


# ---------------------------------------------------------------- 子进程

def _ensure_dirs(patterns, env) -> None:
    """把产物所在的目录先建出来。

    很多导出脚本直接 open(...,"w") 而不建目录，路径一换就 FileNotFoundError。
    建目录是幂等的，不算「猜产物」。
    """
    for pat in patterns:
        try:
            p = Path(resolve(pat.rstrip("/\\"), env))
        except KeyError:
            continue
        # 通配符只到文件名那层，父目录还是确定的
        d = p if pat.endswith(("/", "\\")) else p.parent
        if not any(ch in str(d) for ch in "*?["):
            try:
                d.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass


def _expand_argv(argv) -> list:
    """把命令行里的通配符展开。

    subprocess 不走 shell，`*.dec` 原样传给子进程会被当成一个叫 `*.dec` 的文件。
    没匹配到就保留原样 —— 让子进程自己报「文件不存在」，比静默传空列表好。
    """
    out = []
    for a in argv:
        if any(ch in a for ch in "*?["):
            got = sorted(glob.glob(a))
            out.extend(got if got else [a])
        else:
            out.append(a)
    return out


def _spawn(argv, cwd: Path) -> bool:
    """跑子进程。强制 UTF-8 —— 这是 Windows 上最容易踩的一条。"""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env.pop("PYTHONLEGACYWINDOWSSTDIO", None)

    try:
        p = subprocess.Popen(
            argv, cwd=str(cwd), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
    except FileNotFoundError:
        print(f"  [FAIL] 找不到可执行文件: {argv[0]}")
        print("         若是 python，检查 NIKKE_PY 是否指向 venv 里的解释器。")
        return False

    assert p.stdout is not None
    for line in p.stdout:
        sys.stdout.write("  | " + line)
        if not line.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.flush()               # 长任务要看得到进度，不能等缓冲区满
    p.stdout.close()
    return p.wait() == 0


# ---------------------------------------------------------------- 入口

def main(board: Board) -> int:
    # 本模块的看板是给人看的中文表格。Windows 控制台若是 GBK 代码页、
    # 或输出被重定向到文件，中文会 UnicodeEncodeError 直接崩。
    # 这里统一重设成 UTF-8 + errors=replace：宁可少数几个字变成 ?，也不崩。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    argv = sys.argv[1:]

    # --set KEY=VAL 临时覆盖占位符，免得为了试一条命令去改环境变量
    if "--set" in argv:
        i = argv.index("--set")
        for kv in argv[i + 1:]:
            if "=" not in kv:
                break
            k, v = kv.split("=", 1)
            board.env[k.strip().upper()] = v

    dry = "--dry" in argv

    if "--run" in argv:
        i = argv.index("--run")
        if i + 1 >= len(argv):
            print("--run 后面要跟步骤编号或 all")
            return 2
        return board.run(argv[i + 1], dry)

    return board.show(as_json="--json" in argv)
