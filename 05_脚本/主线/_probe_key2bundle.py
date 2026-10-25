"""探针：验证「资源键 → bundle 名」的 join 规则命中率。

只读，不改任何文件。输出每条规则命中的候选包名，供 build_inventory.py 固化。
"""
import re, os, sys

BASE_KEYS = r"D:\Codex\Nikke\Nikke_Skills\拆包\00_资源库\版本节点\_干跑_20261025\00_基线_键清单"

def load_index():
    """桶 -> [bundle 名]"""
    idx = {}
    for f in os.listdir(BASE_KEYS):
        if not f.endswith("_keys.txt"):
            continue
        bucket = f[:-len("_keys.txt")]
        names = []
        with open(os.path.join(BASE_KEYS, f), encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                n = line.strip()
                if n.endswith(".bundle"):
                    names.append(n)
        idx[bucket] = names
    return idx

# (产物类型, 键格式化模板, 包名前缀正则)
RULES = [
    ("立绘_高清",  "{k}",       r"^icons-char-full\(hd\)_assets_{k}_[0-9a-f]{{32}}\.bundle$"),
    ("立绘",       "{k}",       r"^icons-char-full\(sd\)_assets_{k}_[0-9a-f]{{32}}\.bundle$"),
    ("半身像",     "{k}",       r"^icons-char-mi\(hd\)_assets_mi_{k}_s_[0-9a-f]{{32}}\.bundle$"),
    ("小人立绘",   "{k}",       r"^sdcharacters_assets_{k}_var_[0-9a-f]{{32}}\.bundle$"),
    ("爆裂",       "{k}",       r"^spotskillcutscene_assets_{k}_cut_scene_[0-9a-f]{{32}}\.bundle$"),
]

KEYS = ["c870_00", "c870_01", "c870_02", "c871_00", "c871_01", "c871_02", "c872_00", "c580_00", "c580_01"]

def main():
    idx = load_index()
    allnames = []
    for b, names in idx.items():
        for n in names:
            allnames.append((b, n))
    print(f"索引：{len(idx)} 桶 / {len(allnames)} 个 bundle\n")

    for key in KEYS:
        print(f"=== {key} ===")
        for label, tpl, pat in RULES:
            rx = re.compile(pat.format(k=re.escape(key)))
            hits = [f"{b}:{n}" for b, n in allnames if rx.match(n)]
            print(f"  {label:<10} {len(hits)}  {hits[0] if hits else '—'}")
        # 兜底：裸包含
        loose = [n for b, n in allnames if key in n]
        print(f"  裸包含命中 {len(loose)}")

if __name__ == "__main__":
    main()
