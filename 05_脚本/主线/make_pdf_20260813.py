# -*- coding: utf-8 -*-
"""make_pdf_20260813.py —— 生成 2026-08-13 更新还原报告的 HTML 并打印成 PDF。

本机无 pandoc，走 HTML → Chrome headless → PDF（Prompt §6.2 实测路径）。
图片一律用绝对 file:// URI（相对路径在 headless 下丢图）。
"""
import subprocess
import sys
from pathlib import Path

from PIL import Image

NODE = Path(r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
HTML = NODE / "_报告_20260813.html"
PDF = NODE / "2026-08-13_国际服更新还原报告.pdf"


def uri(p: Path) -> str:
    return p.resolve().as_uri()


def img(p: Path, cls="", cap="") -> str:
    if not p.exists():
        return f'<div class="miss">缺失图片：{p.name}</div>'
    im = Image.open(p)
    c = f' class="{cls}"' if cls else ""
    t = f'<div class="cap">{cap or p.name}</div>' if cap is not False else ""
    return (f'<figure><img src="{uri(p)}"{c} '
            f'alt="{p.name}">'
            f'{t if cap is not False else ""}</figure>'
            f'<!-- {im.size[0]}x{im.size[1]} -->')


def grid(paths, per_row=3, cls="thumb"):
    cells = "".join(f'<div class="cell">{img(p, cls, cap=False)}'
                    f'<div class="cap">{p.stem}</div></div>' for p in paths)
    return f'<div class="grid g{per_row}">{cells}</div>'


BAN = NODE / "05_banner图"
ILL = NODE / "01_活动_PERSONA联动_ce009" / "插画"
CH870 = NODE / "02_新角色" / "QUEEN（真）_c870"
CH871 = NODE / "02_新角色" / "雪子_c871"
SKIN = NODE / "03_新皮肤_5件"

banners = sorted(BAN.glob("*_S.png")) + sorted([p for p in BAN.glob("*.png") if not p.name.endswith("_S.png")])
banners_big = sorted([p for p in BAN.glob("*.png") if not p.name.endswith("_S.png")])
ills = sorted(ILL.glob("*.png"))

COST = [
    ("QUEEN（真）_c870_01_秀尽学园学生会长", "870_01 · QUEEN（真）· 秀尽学园学生会长", "通过活动获得", "c870_01_uc_tex.png"),
    ("QUEEN（真）_c870_02_女王睡衣", "870_02 · QUEEN（真）· 女王睡衣（Ver. NIKKE Collabo）", "通过活动 PASS 获得", "c870_02_uc_tex.png"),
    ("雪子_c871_01_天城屋旅馆和服", "871_01 · 雪子 · 天城屋旅馆和服", "通过活动获得", "c871_01_uc_tex.png"),
    ("雪子_c871_02_冬日雅居", "871_02 · 雪子 · 冬日雅居（Ver. NIKKE Collabo）", "通过活动 PASS 获得", "c871_02_uc_tex.png"),
    ("潘托姆_c580_01_圣洁怪盗", "580_01 · 潘托姆 · 圣洁怪盗", "通过时装抽取获得", "c580_01_uc_tex.png"),
]

CSS = """
@page { size: A4 portrait; margin: 12mm; }
* { box-sizing: border-box; }
body { font-family: "Microsoft YaHei UI","Microsoft YaHei",sans-serif; font-size: 10.5pt;
       color:#1a1a1a; line-height:1.65; margin:0; }
.page { page-break-after: always; }
.page:last-child { page-break-after: auto; }
h1 { font-size: 22pt; margin: 0 0 6pt; letter-spacing:.5pt; }
h2 { font-size: 15pt; margin: 0 0 10pt; padding-bottom: 5pt;
     border-bottom: 2.5pt solid #2f6df6; color:#12325c; }
h3 { font-size: 11.5pt; margin: 14pt 0 6pt; color:#12325c; }
h4 { font-size: 10.5pt; margin: 10pt 0 4pt; color:#33465e; }
p  { margin: 5pt 0; }
table { width:100%; border-collapse: collapse; font-size: 9pt; margin: 6pt 0 10pt; }
th,td { border: .6pt solid #c8d2e0; padding: 4pt 6pt; text-align:left; vertical-align: top; }
th { background:#eef3fb; font-weight:600; color:#12325c; }
tr:nth-child(even) td { background:#fafcff; }
code,kbd { font-family: Consolas,"Courier New",monospace; background:#f2f4f8;
           padding:.5pt 3pt; border-radius:2pt; font-size:8.5pt; color:#0f4c81; }
pre { background:#f6f8fb; border-left:3pt solid #2f6df6; padding:8pt 10pt; font-size:8.5pt;
      font-family: Consolas,monospace; white-space:pre-wrap; line-height:1.5; }
.cover { height: 250mm; display:flex; flex-direction:column; justify-content:center; }
.cover .kicker { color:#2f6df6; font-size:11pt; letter-spacing:2pt; margin-bottom:10pt; }
.cover .sub { font-size:12pt; color:#4a5a70; margin-top:14pt; }
.cover .meta { margin-top:34pt; font-size:9.5pt; color:#5a6a80; border-top:1pt solid #d6dee9; padding-top:12pt; }
.cover .meta div { margin:3pt 0; }
.badge { display:inline-block; background:#2f6df6; color:#fff; font-size:8.5pt;
         padding:2pt 8pt; border-radius:9pt; margin-right:5pt; }
.badge.gray { background:#8a97a8; }
.badge.red  { background:#d94b4b; }
.badge.ok   { background:#2fa36b; }
.grid { display:flex; flex-wrap:wrap; gap:7pt; margin:8pt 0; }
.g3 .cell { width: calc(33.33% - 5pt); }
.g2 .cell { width: calc(50% - 4pt); }
.g4 .cell { width: calc(25% - 6pt); }
.cell { border:.6pt solid #dde4ee; border-radius:3pt; padding:4pt; background:#fff; }
.cell img { width:100%; height:auto; display:block; }
.cap { font-size:7pt; color:#6b7a8c; text-align:center; margin-top:3pt;
       word-break:break-all; line-height:1.3; }
figure { margin:0; }
.kpi { display:flex; gap:8pt; margin:12pt 0; }
.kpi div { flex:1; border:.6pt solid #dde4ee; border-top:3pt solid #2f6df6;
           padding:8pt; text-align:center; border-radius:3pt; }
.kpi b { display:block; font-size:20pt; color:#12325c; line-height:1.2; }
.kpi span { font-size:8pt; color:#6b7a8c; }
.note { background:#fff8e6; border-left:3pt solid #e0a800; padding:8pt 10pt; font-size:9pt; margin:8pt 0; }
.warn { background:#fdeeee; border-left:3pt solid #d94b4b; padding:8pt 10pt; font-size:9pt; margin:8pt 0; }
.ok   { background:#eefaf3; border-left:3pt solid #2fa36b; padding:8pt 10pt; font-size:9pt; margin:8pt 0; }
.two { display:flex; gap:12pt; }
.two > div { flex:1; }
.portrait img { width:100%; max-height:165mm; object-fit:contain; }
.miss { color:#d94b4b; font-size:8pt; border:1pt dashed #d94b4b; padding:10pt; text-align:center; }
footer { position:fixed; bottom:0; font-size:7.5pt; color:#9aa7b6; }
"""


def P(body, cls=""):
    return f'<div class="page {cls}">{body}</div>'


# ---------- 页 1 封面 ----------
p1 = f"""
<div class="cover">
  <div class="kicker">NIKKE · 拆包交付 · 版本节点还原</div>
  <h1>2026-08-13 国际服更新<br>回溯还原报告</h1>
  <div class="sub">PERSONA 联动大版更 · 6/6 内容 1:1 还原</div>
  <div style="margin-top:22pt">
    <span class="badge">预演轮</span>
    <span class="badge gray">回溯采集</span>
    <span class="badge ok">硬链接零副本</span>
  </div>
  <div class="meta">
    <div><b>采集时点</b>：2026-10-25 09:5x（GMT+8）</div>
    <div><b>客户端</b>：com.proximabeta.nikke · 152.8.7（1520807）</div>
    <div><b>设备</b>：e9711d88 / 25102RKBEC / Android 17 / KernelSU root</div>
    <div><b>数据源</b>：saus/raw 文本表（NKDB 解密）+ StaticData_152 静态表 + store.cdb 分块资源</div>
    <div><b>执行</b>：WorkBuddy · 依据《版本更新准备_Prompt_20261029_国际服_v1.4》</div>
  </div>
</div>"""

# ---------- 页 2 一页速览 ----------
p2 = f"""
<h2>一页速览</h2>
<div class="kpi">
  <div><b>6</b><span>新增 banner</span></div>
  <div><b>2</b><span>新角色</span></div>
  <div><b>5</b><span>新皮肤</span></div>
  <div><b>1</b><span>联动活动</span></div>
  <div><b>8</b><span>活动插画</span></div>
  <div><b>21</b><span>剧情路标</span></div>
  <div><b>6</b><span>技能</span></div>
</div>
<p>本期是 <b>PERSONA 系列联动大版更</b>：P5 的 Queen（真·新岛）与 P4 的天城雪子 双角色联动，配套 Phantom（潘托姆）转盘皮、2 张联动 Event PASS、ce009「PERSONA ON FRONTLINE」活动。</p>
<h3>当期 6 张 banner</h3>
{grid(banners_big, 2)}
<div class="note">判据：<code>event_260813.lsc</code> 与相邻期的 <code>sprite.name</code> 集合差。分片只装「该期新上架」的 banner，被替换的就消失，所以集合差 = 当期的商业化内容。</div>"""

# ---------- 页 3 分期原理 ----------
p3 = """
<h2>为什么能准确定位「这期上了什么」</h2>
<p><code>saus/raw</code> 里存在 <b>10 张按更新日期命名</b>的文本包，天然就是分期快照：</p>
<pre>event_260423  event_260514  event_260528  event_260611  event_260702
event_260723  event_260813  event_260903  event_260917  event_261008</pre>
<table>
<tr><th style="width:22%">表</th><th style="width:30%">列</th><th>内容</th></tr>
<tr><td><code>sprite</code></td><td>id, name, width, height, last, <b>texture</b></td><td>该期活动 BANNER 图（1108×368 + 328×108 两版）</td></tr>
<tr><td><code>locale</code></td><td>key, code, sprite</td><td>上述图的多语言键（9 语言）</td></tr>
</table>
<h3>这条链路的三个优点</h3>
<table>
<tr><th style="width:18%">维度</th><th style="width:41%">event 分片链</th><th>catalog / 静态表 diff</th></tr>
<tr><td>覆盖</td><td>池子、皮肤、PASS、活动</td><td>框、称号、主线、地图、插画 HD</td></tr>
<tr><td>耗时</td><td><b>分钟级</b></td><td>小时级（需先取基线）</td></tr>
<tr><td>依赖基线</td><td><b>不需要</b></td><td>必须</td></tr>
<tr><td>误报风险</td><td>低（集合差）</td><td>中（命名/hash 会变）</td></tr>
</table>
<div class="ok"><b>对 10-29 的直接价值</b>：开服后第一件事拉当天分片（约 1.5 MB，秒级），5 分钟内就能出「这天上了哪些池子/皮肤/PASS/活动」的清单——即使 20 GB 全量基线出问题，内容清单也不受影响。</div>
<div class="warn"><b>但必须当天拉</b>：若哪天更新后分片总数没增加、而旧分片消失，说明旧分片会被清理。8-13 这期现在还能回溯，纯粹因为它还在。</div>
<h3>命名规律（已解，可直接复用）</h3>
<table>
<tr><th style="width:40%">banner 前缀</th><th>含义</th><th>反查目标</th></tr>
<tr><td><code>GACHA_C&lt;NNN&gt;</code></td><td>角色 NNN 的卡池（<b>C 后数字 = cID</b>）</td><td><code>Locale_Character:&lt;NNN&gt;_name</code></td></tr>
<tr><td><code>GACHA_RE_C&lt;NNN&gt;</code></td><td>复刻卡池</td><td>同上</td></tr>
<tr><td><code>COSTUME_GACHA_C&lt;NNN&gt;_&lt;MM&gt;</code></td><td>角色 NNN 第 MM 套皮肤的时装抽取（转盘）</td><td><code>Locale_CharacterCostume:&lt;NNN&gt;_0&lt;MM&gt;_costume_name</code></td></tr>
<tr><td><code>&lt;CODE&gt;_PASS</code></td><td>活动通行证 CODE</td><td>皮肤 <code>_N_description</code> 里的 <code>Obtained from an Event Pass.</code></td></tr>
<tr><td><code>&lt;CODE&gt;</code> / <code>_&lt;NN&gt;</code></td><td>剧情/联动活动</td><td><code>TrailMarkerEventTable</code> / <code>EventManagerTable</code></td></tr>
<tr><td><code>GACHA_SELECT_&lt;NN&gt;</code></td><td>自选卡池</td><td><code>GachaSelectupListTable</code></td></tr>
</table>"""

# ---------- 页 4-5 六项还原 ----------
rows6 = [
    ("1", "EVENT_BANNER_GACHA_C870", "新角色卡池", "870 · QUEEN（真）", "Queen (Makoto)", "CV 佐藤利奈；SSR；爆裂 III"),
    ("2", "EVENT_BANNER_GACHA_C871", "新角色卡池", "871 · 雪子", "Yukiko", "CV 小清水亚美；SSR；爆裂 III"),
    ("3", "EVENT_BANNER_COSTUME_GACHA_C580_01", "时装抽取（转盘）", "580 · 潘托姆「圣洁怪盗」", "Saint Thief", "既有角色 + 新皮肤，不是新角色"),
    ("4", "EVENT_BANNER_THIEFQUEEN_PASS", "活动 PASS", "870_02 ·「女王睡衣」", "Queen's Pajamas", "Obtained from an Event Pass."),
    ("5", "EVENT_BANNER_SNOWFLAKES_PASS", "活动 PASS", "871_02 ·「冬日雅居」", "Winter Roomwear", "Obtained from an Event Pass."),
    ("6", "EVENT_BANNER_TRAILMARKER_01", "Trail Marker 活动", "ce009 · PERSONA ON FRONTLINE", "EventId 230001", "关联主线 595 → 解锁第 49 章"),
]
tb = "".join(f"<tr><td>{a}</td><td><code>{b}</code></td><td>{c}</td><td><b>{d}</b></td><td>{e}</td><td>{f}</td></tr>"
             for a, b, c, d, e, f in rows6)
p4 = f"""
<h2>六项 banner 逐条还原</h2>
<p>6 个 banner <b>全部落到具体内容，无一悬空</b>。下表每一行都能在 <code>06_证据/01_文本证据.tsv</code> 找到原文键值。</p>
<table>
<tr><th style="width:5%">#</th><th style="width:26%">banner 代号</th><th style="width:14%">类型</th>
    <th style="width:20%">还原结果</th><th style="width:13%">英文名/ID</th><th>证据</th></tr>
{tb}
</table>
<h3>两个必须记住的坑</h3>
<div class="warn">
<b>坑 1 · 活动名不能用 EventManagerTable 取。</b><br>
8-13 这 6 行的 <code>NameLocalkey</code> 全部指向 <code>Locale_Event:story_event_name_001</code>，值是
「<b>NO CALLER ID</b>」——这是新事件系统的共用占位键，不是本期实名。实名必须从
<code>eventscene_ce009_*</code> / <code>event_ce009_*</code> 文本族取。
</div>
<div class="warn">
<b>坑 2 · 英文名里有不换行空格。</b><br>
<code>870_01_costume_name</code> = <code>Shujin&#92;u00a0Academy&#92;u00a0Student&#92;u00a0Council&#92;u00a0President</code>。
直接字符串比对会判"键不存在"，必须先归一化 NBSP。
</div>
<h3>技能键的新规律（可直接用于 10-29 三个新角色）</h3>
<p><code>CharacterTable</code> 的 <code>UltiSkillId / Skill1Id / Skill2Id</code> 前 5 位 = <code>Locale_Skill</code> 的键前缀：</p>
<table>
<tr><th>角色</th><th>UltiSkillId</th><th>→ 爆裂键</th><th>Skill1Id</th><th>→ 技能1键</th><th>Skill2Id</th><th>→ 技能2键</th></tr>
<tr><td>870</td><td>1870301</td><td><code>18703</code></td><td>2870101</td><td><code>28701</code></td><td>2870201</td><td><code>28702</code></td></tr>
<tr><td>871</td><td>1871301</td><td><code>18713</code></td><td>2871101</td><td><code>28711</code></td><td>2871201</td><td><code>28712</code></td></tr>
</table>
<p>以前靠「猜技能键名」的做法可以彻底放弃，这条规律是确定性的。</p>"""

# ---------- 页 6 活动 ----------
p6 = f"""
<h2>活动 · ce009「PERSONA ON FRONTLINE」</h2>
<div class="two">
  <div>
    <table>
    <tr><th style="width:36%">项</th><th>值</th></tr>
    <tr><td>活动代号</td><td><code>ce009</code></td></tr>
    <tr><td>活动名</td><td><b>PERSONA ON FRONTLINE</b></td></tr>
    <tr><td>EventId</td><td><code>230001</code>（EventSystemType 63）</td></tr>
    <tr><td>活动资源</td><td><code>event_scene_trail_marker_01</code></td></tr>
    <tr><td>分片</td><td><code>event_260813.lsc</code></td></tr>
    <tr><td>banner</td><td><code>EVENT_BANNER_TRAILMARKER_01</code></td></tr>
    <tr><td>关联主线</td><td><code>MainQuestId 595</code>（<code>d_main_48_07</code>）→ 解锁第 <b>49</b> 章</td></tr>
    <tr><td>插画</td><td>8 张（1024×1024）</td></tr>
    <tr><td>剧情路标</td><td>21 条</td></tr>
    </table>
    <div class="ok"><b>联动归属的文本级证据</b>：路标文本里出现「宿舍使用守则 · 宵禁 23:59」「看完电视请关闭电源」→ P4 的电视世界；「女仆咖啡厅 · 怪盗必须随时掌握多个逃生出口」→ P5。雪子台词「小熊在做什么呢」（Teddie）进一步锁定 P4。</div>
  </div>
  <div>
    {img(NODE / "01_活动_PERSONA联动_ce009" / "banner" / "EVENT_BANNER_TRAILMARKER_01.png", "", "活动 banner 1108×368")}
  </div>
</div>
<h3>活动插画 8 张（1024×1024）</h3>
{grid(ills, 4)}
<p style="font-size:8.5pt;color:#6b7a8c">交叉校验：catalog 键清单里 <code>scenariobackground(hd)_assets_eventscene_ce009_*</code> 恰好 8 条，与本页图片数一致。</p>"""

# ---------- 页 7 角色 870 ----------
p7 = f"""
<h2>新角色 ① · QUEEN（真）· c870</h2>
<div class="two">
  <div class="portrait" style="flex:0 0 40%">
    {img(CH870 / "立绘_HD" / "c870_00_uc_tex.png", "", "c870_00 立绘 HD（未和谐 2048²）")}
  </div>
  <div>
    <table>
    <tr><th style="width:34%">项</th><th>值</th></tr>
    <tr><td>cID</td><td><code>870</code></td></tr>
    <tr><td>英 / 中 / 日</td><td>Queen (Makoto) / QUEEN（真） / クイーン（真）</td></tr>
    <tr><td>CV</td><td>佐藤利奈 / Rina Sato</td></tr>
    <tr><td>稀有度</td><td>SSR（OriginalRare = 3）</td></tr>
    <tr><td>爆裂阶段</td><td>III（UseBurstSkill = 3）</td></tr>
    <tr><td>CharacterTable.Id</td><td>587001（11 成长档）</td></tr>
    <tr><td>Corporation / Class</td><td>7 / 1（<b>未做中文映射</b>）</td></tr>
    <tr><td>ElementId</td><td>100001</td></tr>
    <tr><td>Squad</td><td>72</td></tr>
    </table>
    <p style="font-size:9pt"><b>简介</b>：全名为新岛真。秀尽学园的学生会长，同时也是「心之怪盗团」的智囊。个性冷静、责任感强，行动力十足，但也因为过于认真而有不懂变通的一面。</p>
  </div>
</div>
<h3>技能 3 个</h3>
<table>
<tr><th style="width:10%">序</th><th style="width:31%">名称（英 / 中 / 日）</th><th>效果要点</th></tr>
<tr><td><b>爆裂</b><br><code>18703</code></td><td>Mafreidyne<br>玛哈芙雷达因<br>マハフレイダイン</td>
<td>对全体敌人：最终攻击力 X% 的<b>分摊伤害</b>。若存在<b>风压代码</b>敌人 → 1MORE：自身攻击力 X% ▲，持续 X 秒。</td></tr>
<tr><td><b>技能1</b><br><code>28701</code></td><td>Persona: Johanna<br>人格面具：琼安<br>ペルソナ：ヨハンナ</td>
<td>战斗开始获得【人格面具-琼安】（持续·无法解除）：<b>核热强化</b>优越代码攻击伤害▲ + <b>防御诀窍</b>防御力▲。<br>战斗开始 &amp; 全爆裂结束：攻击力▲。<br><b>1MORE 生效</b> / <b>追击生效</b>时：对全体敌人分摊伤害。</td></tr>
<tr><td><b>技能2</b><br><code>28702</code></td><td>Fist of Justice!<br>铁・拳・制・裁！<br>鉄・拳・制・裁！</td>
<td>战斗开始：攻击伤害▲。<br>使用爆裂技能时获得【铁・拳・制・裁！】：<b>高级核热强化</b> + <b>拉库卡加</b>防御▲，全爆裂结束解除。<br>进入爆裂 3 阶：分摊伤害▲。<br><b>1MORE 生效</b>：对 B3 且人格面具状态的队友【<b>换手</b>】攻击力▲（可叠）。</td></tr>
</table>
<div class="note">技能名逐字取自 <code>Locale_Skill</code>（含全角冒号「：」与「！」）。<b>倍率/CD 实值未取</b>：<code>Locale_Skill</code> 只有文案占位符 <code>{{description_value_XX}}</code>，实值在 <code>CharacterSkillTable</code>/<code>SkillInfoTable</code>，mpdump 尚未导出这两张表 —— 未取就不填空。</div>"""

# ---------- 页 8 角色 871 ----------
p8 = f"""
<h2>新角色 ② · 雪子 · c871</h2>
<div class="two">
  <div class="portrait" style="flex:0 0 40%">
    {img(CH871 / "立绘_HD" / "c871_00_uc_tex.png", "", "c871_00 立绘 HD（未和谐 2048²）")}
  </div>
  <div>
    <table>
    <tr><th style="width:34%">项</th><th>值</th></tr>
    <tr><td>cID</td><td><code>871</code></td></tr>
    <tr><td>英 / 中 / 日</td><td>Yukiko / 雪子 / 雪子</td></tr>
    <tr><td>CV</td><td>小清水亚美 / Ami Koshimizu</td></tr>
    <tr><td>稀有度</td><td>SSR（OriginalRare = 3）</td></tr>
    <tr><td>爆裂阶段</td><td>III（UseBurstSkill = 3）</td></tr>
    <tr><td>CharacterTable.Id</td><td>587101（11 成长档）</td></tr>
    <tr><td>Corporation / Class</td><td>7 / 1（<b>未做中文映射</b>）</td></tr>
    <tr><td>ElementId</td><td>100001</td></tr>
    <tr><td>Squad</td><td>73</td></tr>
    </table>
    <p style="font-size:9pt"><b>简介</b>：全名为天城雪子。八十神高中「自称特别搜查队」成员，天城屋旅馆老板娘的女儿，正努力学习接班。头脑灵活但不太擅长察言观色。</p>
  </div>
</div>
<h3>技能 3 个</h3>
<table>
<tr><th style="width:10%">序</th><th style="width:31%">名称（英 / 中 / 日）</th><th>效果要点</th></tr>
<tr><td><b>爆裂</b><br><code>18713</code></td><td>Maragidyne<br>玛哈拉基达因<br>マハラギダイン</td>
<td>对全体敌人：最终攻击力 X% 的<b>分摊伤害</b>。若存在<b>风压代码</b>敌人 → 1MORE：自身攻击力 X% ▲。</td></tr>
<tr><td><b>技能1</b><br><code>28711</code></td><td>Persona: Konohana Sakuya<br>人格面具：木花咲耶<br>ペルソナ：コノハナサクヤ</td>
<td>战斗开始获得【人格面具-木花咲耶】：每 X 秒对全体队友【<b>梅迪亚</b>】恢复最终最大体力 X%。<br>战斗开始 &amp; 全爆裂结束：攻击力▲。<br><b>1MORE 生效</b>：对全体敌人分摊伤害。</td></tr>
<tr><td><b>技能2</b><br><code>28712</code></td><td>Scarlet Flower<br>华焰<br>真紅の華</td>
<td>战斗开始：攻击伤害▲。<br>使用爆裂技能时获得【华焰】：每 X 秒全体【<b>梅迪拉玛</b>】恢复 + 自身【<b>火焰强化</b>】分摊伤害▲ + 【<b>深红守护</b>】受<b>水冷</b>代码敌人伤害▼。<br>进入爆裂 3 阶：优越代码攻击伤害▲。<br><b>1MORE 生效</b>：对队友【<b>追击</b>】攻击力▲。</td></tr>
</table>
<h3>好感度台词（各 6 条 speech + 2 条 stay，全量见证据表）</h3>
<table>
<tr><th style="width:16%">键</th><th>简体中文</th></tr>
<tr><td><code>871_speech_01</code></td><td>我还是不敢相信……这里不是电视里，而是另一个世界……对吧？</td></tr>
<tr><td><code>871_speech_05</code></td><td>这次我要和艾玛小姐一起练习做菜。方便的话，要一起去吗？</td></tr>
<tr><td><code>871_stay_01</code></td><td>话说回来，小熊在做什么呢……？去看看他的情况吧。</td></tr>
</table>
<p style="font-size:8.5pt;color:#6b7a8c">「电视里」「小熊（Teddie）」是 P4 原生设定，可作为 ce009 联动归属的台词级证据。</p>"""

# ---------- 皮肤（每 2 件一页） ----------
def skin_block(dirname, title, how, fname):
    d = SKIN / dirname
    return f"""
<div class="two" style="margin-bottom:14pt">
  <div class="portrait" style="flex:0 0 55%">{img(d / f"HD_{fname}", "", f"{fname}")}</div>
  <div>
    <h3 style="margin-top:0">{title}</h3>
    <table>
    <tr><th style="width:30%">项</th><th>值</th></tr>
    <tr><td>目录</td><td style="word-break:break-all;font-size:8pt"><code>{dirname}</code></td></tr>
    <tr><td>获取方式</td><td><b>{how}</b></td></tr>
    <tr><td>HD</td><td style="font-size:8pt"><code>HD_{fname}</code></td></tr>
    <tr><td>SD</td><td style="font-size:8pt"><code>SD_{fname.replace("_uc_tex","")}</code></td></tr>
    </table>
  </div>
</div>"""

skin_pages = []
for i in range(0, len(COST), 2):
    chunk = COST[i:i+2]
    body = "".join(skin_block(*c) for c in chunk)
    skin_pages.append(f"<h2>新皮肤（{i+1}–{i+len(chunk)} / 5）</h2>" + body +
                      ('<div class="note">获取方式来自 <code>Locale_CharacterCostume</code> 的 <code>_N_description</code> 固定句式：'
                       '<code>Obtained from an Event Pass.</code> / <code>Obtained from an event.</code> / '
                       '<code>Obtained from the Costume Gacha.</code></div>' if i == 0 else ""))

# ---------- 页 14 系统层 ----------
p14 = """
<h2>系统层 · 为什么这期回溯不出来</h2>
<p>这一页是<b>如实报缺口</b>，不是遗漏。10-29 正式轮不会缺这块。</p>
<table>
<tr><th style="width:26%">项</th><th style="width:14%">能否回溯 8-13</th><th>原因</th></tr>
<tr><td>个突头像框</td><td><span class="badge red">否</span></td><td><code>UserFrameTable</code> 是<b>当前版本全量快照</b>，8-13 到 10-25 之间所有新增框都混在里面，没有任何字段记录"哪一期上线"</td></tr>
<tr><td>个人主页称号</td><td><span class="badge red">否</span></td><td>同上（<code>UserTitleTable</code> / <code>UserTitleAssemblyTable</code> / <code>Locale_Profile:title_*</code>）</td></tr>
<tr><td>主线章节增量</td><td><span class="badge gray">部分</span></td><td>能证「595 打完开放第 49 章」，不能证「第 49 章是这期上的」</td></tr>
</table>
<div class="warn"><b>根本原因</b>：这三类都是「静态表全量替换」，不是「按分片增量下发」。判增量唯一办法是<b>有更新前的表做行差</b>——8-13 之前我们没抓过。这正是 10-29 前「基线快照」被列为必做项的原因。</div>
<h3>当前状态基线（152.8.7，可当 10-29 的对照起点）</h3>
<table>
<tr><th style="width:38%">表</th><th style="width:14%">行数</th><th>备注</th></tr>
<tr><td><code>UserFrameTable</code></td><td><b>326</b></td><td>唯一 ResourceId <b>236</b>；<code>SubResourceId</code> 是多部件框机制</td></tr>
<tr><td><code>UserTitleTable</code></td><td><b>250</b></td><td><code>IconResourceId</code> 指图标</td></tr>
<tr><td><code>UserTitleAssemblyTable</code></td><td><b>182</b></td><td>可装配称号，与上表口径不同</td></tr>
<tr><td><code>Locale_Profile:title_*</code></td><td>约 <b>75</b></td><td>称号显示文本</td></tr>
</table>
<h3>「国际服有没有动态头像框」——上一轮的结论已推翻</h3>
<div class="ok">现在的判据是：<b>头像框判据上移到 <code>UserFrameTable</code>，两服通用</b>。是否存在多帧由 <code>SubResourceId</code> 是否指向序列帧资源决定，不靠"国际服/国服"区分。<br>
因此 <b>10-29 不需要给国际服单独写一套规则</b>，只需在新 ResourceId 上判断有没有序列帧子资源。若实测出现"国际服只有静态、国服同 ID 有序列帧"的单框特例，再按特例登记。</div>
<h3>10-29 这块怎么做</h3>
<pre>1. 开服后重新导出 UserFrameTable / UserTitleTable / UserTitleAssemblyTable
2. 与 00_基线_静态表\\ 同名 JSON 做行差：
   新 ResourceId 集合 = 新增框（按 ResourceId 去重，不按行数）
   新 Id 集合       = 新增称号
3. 新 ResourceId → catalog 键 icons-user_frame* → 重链路导出 PNG / 序列帧
4. 新增称号 → IconResourceId → icons-user_title* → 导出图标
5. 每步留「键 → hash → 导出行数」三元组</pre>"""

# ---------- 页 15 证据与校验 ----------
p15 = """
<h2>证据与校验</h2>
<h3>1. 文本证据 34 条（缺失 0）</h3>
<p><code>06_证据/01_文本证据.tsv</code>：每条含「键 / 英文 / 简体中文 / 日文 / 来源表」五列，全部可在客户端表内逐行核对。</p>
<table>
<tr><th style="width:26%">类别</th><th style="width:12%">条数</th><th>内容</th></tr>
<tr><td>角色</td><td>8</td><td>870/871/580 的 name + description + cv_en + cv_ja</td></tr>
<tr><td>皮肤</td><td>10</td><td>5 件 ×（costume_name + N_description）</td></tr>
<tr><td>技能</td><td>12</td><td>6 个技能 ×（name + description）</td></tr>
<tr><td>CV 缺失</td><td>0</td><td>注意：无单一 <code>NNN_cv</code> 键，只有 <code>_cv_en/_cv_ja/_cv_ko</code></td></tr>
</table>
<h3>2. 跨源一致性校验</h3>
<table>
<tr><th style="width:44%">校验项</th><th style="width:16%">值 A</th><th style="width:16%">值 B</th><th>结论</th></tr>
<tr><td>皮肤总数</td><td><code>Locale_CharacterCostume</code> 183</td><td><code>CharacterCostumeTable</code> 183</td><td><span class="badge ok">一致</span></td></tr>
<tr><td>活动插画数</td><td>本地 8 张</td><td>catalog <code>eventscene_ce009_*</code> 8 条</td><td><span class="badge ok">一致</span></td></tr>
<tr><td>本期事件行数</td><td><code>EventManagerTable</code> 中 <code>event_260813</code> 资源 6 行</td><td>banner 6 个</td><td><span class="badge ok">一致</span></td></tr>
<tr><td>技能键推导</td><td><code>UltiSkillId 1870301</code></td><td><code>Locale_Skill:18703_name</code> 存在</td><td><span class="badge ok">一致</span></td></tr>
</table>
<h3>3. 硬链接零副本校验</h3>
<table>
<tr><th style="width:30%">类别</th><th style="width:12%">条目</th><th>硬链接源目录</th></tr>
<tr><td>banner 全量</td><td>12</td><td><code>版本节点/_干跑_20261025/06_预演数据/banner_260813/</code></td></tr>
<tr><td>banner 活动</td><td>2</td><td>同上</td></tr>
<tr><td>活动插画</td><td>8</td><td><code>剧情插画/联动/</code></td></tr>
<tr><td>角色立绘 SD</td><td>6</td><td><code>角色立绘/</code></td></tr>
<tr><td>角色立绘 HD</td><td>6</td><td><code>角色立绘HD/</code></td></tr>
<tr><td>角色 SD 立绘</td><td>24</td><td><code>角色SD立绘/</code></td></tr>
<tr><td>角色 SI</td><td>6</td><td><code>角色立绘SI/</code></td></tr>
<tr><td>皮肤立绘</td><td>10</td><td><code>角色立绘HD/</code> + <code>角色立绘/</code></td></tr>
<tr><td><b>合计</b></td><td><b>74</b></td><td>全部 <code>os.link</code> 硬链接，同盘 D:，<b>不额外占盘</b></td></tr>
</table>
<div class="ok">清单 <code>06_证据/06_硬链接清单.tsv</code> 逐条记录 <b>inode / nlink / sha256前16</b>，可验证"目标与源是同一实体"（同 inode 即同一份数据）。<br>
冲突 0 条。SD 立绘的共用纹理 <code>ground.png</code>、<code>SDToon_Tex_RimDefault.png</code> 在每个 skin 目录下同名，已加 <code>c&lt;ID&gt;_&lt;序号&gt;__</code> 前缀区分。</div>
<h3>4. 复跑一致性</h3>
<pre>python pull_lsc.py Locale_Character Locale_CharacterCostume Locale_Skill \\
                  Locale_Event Locale_Profile perm_gacha perm_pass
python build_node_20260813.py      # → 34 / 3 / 183 / 21
python link_resources.py           # → 幂等：已存在同 inode 50 条</pre>"""

# ---------- 页 16 风险与待确认 ----------
p16 = """
<h2>已知限制与待确认</h2>
<h3>本包未解决（不要当成已完成）</h3>
<table>
<tr><th style="width:6%">#</th><th style="width:30%">项</th><th>现状</th></tr>
<tr><td>1</td><td>头像框 / 称号 / 主线增量</td><td>无 8-13 时点基线，<b>结构性不可回溯</b></td></tr>
<tr><td>2</td><td>技能倍率 / CD 实值</td><td>未取。需给 mpdump 加 <code>CharacterSkillTable</code> / <code>SkillInfoTable</code> 导出（<code>StaticData_152_plain.zip</code> 内有 <code>.mpk</code>）</td></tr>
<tr><td>3</td><td>卡池 UP 构成</td><td><code>GachaSelectupListTable.CharacterId</code> 6 位编码与 cID 映射未解</td></tr>
<tr><td>4</td><td>活动 UI 背景包</td><td><code>icons-trailmarker_bg(hd)/(sd)</code> 已定位键，未解包</td></tr>
<tr><td>5</td><td><code>store.cdb.idx</code> 缺约 6,400 条</td><td>导致 <code>icons-user_frame(sd)</code> 取不全</td></tr>
<tr><td>6</td><td>PC（WeGame）版 lss 结构</td><td>未验证，本次全程只做安卓国际服</td></tr>
</table>
<h3>10-29 正式轮开工前必须确认（不确认就停）</h3>
<table>
<tr><th style="width:6%">#</th><th style="width:34%">事项</th><th>为什么</th></tr>
<tr><td>C1</td><td><b>官方停服 / 开服确切时刻</b></td><td>报告里不许写推测的时间，用户未给定</td></tr>
<tr><td>C2</td><td><code>_基线/20261025_国际服/</code> 全量快照是否完成</td><td>没有基线，框/称号/主线全判不出来</td></tr>
<tr><td>C3</td><td><code>_基线_静态表\</code> 那 10 张表是否还在、能否解析</td><td>判「框/称号/皮肤/卡池」的第一判据</td></tr>
<tr><td>C4</td><td>开服后 <code>event_261029.lsc</code> 是否出现</td><td>若出现 → 5 分钟出清单；若旧分片减少 → 必须立刻拉</td></tr>
<tr><td>C5</td><td><code>store.cdb.idx</code> 缺失条目是否已修</td><td>不修则头像框会缺图</td></tr>
<tr><td>C6</td><td>计算器「头像预览模块」的数据目录 / 清单格式 / 裁切规范</td><td>按 Prompt §7：定位不到就停，禁止新建目录试探</td></tr>
</table>
<h3>本包 vs 10-29 正式轮</h3>
<table>
<tr><th style="width:22%">维度</th><th style="width:39%">本包（8-13 预演）</th><th>10-29 正式轮</th></tr>
<tr><td>目标期分片</td><td>事后可回溯（分片仍在）</td><td><b>当天立刻拉</b>，不可等</td></tr>
<tr><td>系统层判据</td><td>结构缺失</td><td>靠 <code>00_基线_静态表\</code> 做行差</td></tr>
<tr><td>美术</td><td>全部在库，硬链接即可</td><td>banner 轻链路；立绘重链路（catalog→store.cdb→UnityPy）</td></tr>
<tr><td>交付物</td><td>本目录 + 本 PDF</td><td>同结构 + 20~40 页 PDF + 头像上传清单</td></tr>
</table>
<div class="note"><b>一句话总结</b>：商业化层 6/6 全还原、角色/皮肤/技能/活动美术全部拿到手；系统层（框/称号）结构上回溯不了，如实标注。流程本身经过一次真实更新检验，可以作为 10-29 的执行依据。</div>"""

pages = [p1, p2, p3, p4, p6, p7, p8] + skin_pages + [p14, p15, p16]
html = ("<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        f"<title>2026-08-13 国际服更新还原报告</title><style>{CSS}</style></head><body>"
        + "".join(P(x) for x in pages) + "</body></html>")
HTML.write_text(html, encoding="utf-8")
print(f"[1] HTML {HTML.name} {len(html):,} 字符，{len(pages)} 页")

cmd = [CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
       "--no-sandbox", "--allow-file-access-from-files",
       f"--print-to-pdf={PDF}", HTML.resolve().as_uri()]
r = subprocess.run(cmd, capture_output=True, timeout=300)
print(f"[2] chrome rc={r.returncode} stderr={r.stderr.decode('utf-8','replace')[:300]}")
if PDF.exists():
    print(f"[3] PDF {PDF.name} {PDF.stat().st_size:,}B")
else:
    sys.exit("PDF 未生成")
