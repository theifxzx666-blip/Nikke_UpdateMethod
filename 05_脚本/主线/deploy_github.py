# -*- coding: utf-8 -*-
"""
把 3D 查看器部署到 GitHub Pages。

做四件事：建仓库 → push → 开 Pages → 等构建完成。

需要一个有 `repo` 权限的 classic token（fine-grained token 不支持建仓库端点）。

用法：
  python deploy_github.py --token ghp_xxxx
  python deploy_github.py --token ghp_xxxx --repo Nikke_Lecher_3D
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO_DIR = r"D:\Codex\临时\nikke_intl_20261029\deploy_lecher3d"
OWNER = "theifxzx666-blip"
API = "https://api.github.com"


def call(method, path, token, body=None):
    url = API + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"message": raw.decode("utf-8", "replace")[:300]}


def run(cmd, cwd=None):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True)
    ap.add_argument("--repo", default="Nikke_Lecher_3D")
    ap.add_argument("--desc", default="NIKKE 47/48 章关底 BOSS（安尼希利奥 / 莉贝雷利奥躯体）1·2 阶段 3D 查看器，带骨骼动画与 GIF 导出")
    a = ap.parse_args()
    token, repo = a.token.strip(), a.repo

    # 1. 身份与权限
    st, me = call("GET", "/user", token)
    if st != 200:
        print("token 无效：", me.get("message"))
        return 1
    login = me["login"]
    print(f"账号：{login}")

    # 2. 建仓库（已存在就复用）
    st, r = call("GET", f"/repos/{login}/{repo}", token)
    if st == 200:
        print(f"仓库已存在，复用：{r['html_url']}")
    else:
        st, r = call("POST", "/user/repos", token, {
            "name": repo, "description": a.desc, "private": False,
            "has_issues": True, "has_wiki": False, "auto_init": False,
        })
        if st not in (200, 201):
            print("建仓库失败：", r.get("message"))
            print("提示：建仓库需要 classic token（勾 repo），fine-grained token 不支持这个端点。")
            return 2
        print(f"仓库已创建：{r['html_url']}")

    # 3. push
    if not os.path.isdir(os.path.join(REPO_DIR, ".git")):
        print("本地仓库不存在：", REPO_DIR)
        return 3
    auth_url = f"https://{login}:{token}@github.com/{login}/{repo}.git"
    run(["git", "remote", "remove", "origin"], cwd=REPO_DIR)
    rc, out = run(["git", "remote", "add", "origin", auth_url], cwd=REPO_DIR)
    if rc:
        print("设置 remote 失败：", out)
        return 4

    print("推送中（约 16 MB）…")
    rc, out = run(["git", "-c", "http.version=HTTP/1.1", "push", "-u", "origin", "main"],
                  cwd=REPO_DIR)
    out = out.replace(token, "***")
    print(out.strip()[-1200:])
    if rc:
        print("推送失败")
        run(["git", "remote", "set-url", "origin",
             f"https://github.com/{login}/{repo}.git"], cwd=REPO_DIR)
        return 5
    run(["git", "remote", "set-url", "origin",
         f"https://github.com/{login}/{repo}.git"], cwd=REPO_DIR)   # 抹掉 token

    # 4. 开 Pages
    st, r = call("GET", f"/repos/{login}/{repo}/pages", token)
    if st == 200:
        print("Pages 已开启：", r.get("html_url"))
    else:
        st, r = call("POST", f"/repos/{login}/{repo}/pages", token,
                     {"source": {"branch": "main", "path": "/"}})
        if st in (200, 201):
            print("Pages 已开启：", r.get("html_url"))
        else:
            print("开 Pages 失败：", r.get("message"))
            print("可手动开：https://github.com/%s/%s/settings/pages" % (login, repo))
            return 6

    # 5. 等构建
    print("等待 Pages 构建…")
    url = f"https://{login}.github.io/{repo}/"
    for i in range(40):
        st, r = call("GET", f"/repos/{login}/{repo}/pages/builds/latest", token)
        s = r.get("status") if st == 200 else "?"
        print(f"  [{i*6:3d}s] {s}")
        if s == "built":
            break
        time.sleep(6)

    # 6. 校验可达
    for _ in range(20):
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=20) as resp:
                if resp.status == 200:
                    print("\n部署完成：" + url)
                    return 0
        except Exception:
            pass
        time.sleep(6)

    print("\nPages 已提交，但站点暂时还没返回 200（首次构建有时要几分钟）：" + url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
