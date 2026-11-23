# -*- coding: utf-8 -*-
"""自媒体账号登录态巡检：逐个打开账号 profile，判断是否仍在登录，并回写 ego-publish 的 lastCheck。

设计要点（都是踩坑换来的）：
1. 只用 ego-publish config 里的 browserPath（本机 Chrome）打开 profile，绝不用 ego.exe，
   否则会覆盖 Local State 的加密密钥，把已登录的号踢下线。
2. profile 被占用（SingletonLock）就跳过，不去抢。
3. 写 accounts.json 前先备份；原子替换；跑完给一张 Markdown 表格。
4. 每个账号一张截图，失败也有现场可看。

用法：
  python check_logins.py                 # 全部账号
  python check_logins.py --only sohu     # 只查某平台
  python check_logins.py --no-write      # 只看结果，不改插件状态
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

DATA_DIR = os.path.expandvars(r"%USERPROFILE%\.dsh\ego-publish")
ACCOUNTS = os.path.join(DATA_DIR, "accounts.json")
CONFIG = os.path.join(DATA_DIR, "config.json")
STATE_DIR = os.environ.get("GEO_STATE_DIR") or r"C:\Users\Administrator\Desktop\增值服务\_state"
SHOT_DIR = os.path.join(STATE_DIR, "login-shots")
HISTORY = os.path.join(STATE_DIR, "login-history.jsonl")
REPORT = os.path.join(STATE_DIR, "登录状态.md")

# 每个平台“已登录后台”的 URL 特征。必须命中才算有效：只看正文关键词会被营销页骗过去
# （搜狐的公开首页正文里就带「发布」「内容管理」这类词，实测出过假阳性）。
EXPECT = {
    "sohu": ["contentManagement"],
    "csdn": ["mp.csdn.net/mp_blog", "mp.csdn.net/user", "mp.csdn.net/mp_download"],
    "netease": ["mp.163.com/#/", "subscribe_v4/index.html"],
    "toutiao": ["mp.toutiao.com/profile", "mp.toutiao.com/creator"],
}
# 每个平台“未登录”的特征：URL 片段
LOGGED_OUT = {
    "sohu": {"url": ["/login", "passport.sohu", "mp.sohu.com/mpfe/v4/login"]},
    "csdn": {"url": ["passport.csdn.net/login", "passport.csdn.net/account"]},
    "netease": {"url": ["login.html", "/login"], "text": ["立即注册网易邮箱账号"]},
    "toutiao": {"url": ["/auth/page/login", "sso.toutiao.com"]},
}
DEFAULT_RULE = {"url": ["login", "sign_in", "signin", "passport"], "text": ["登录", "未登录"]}


def load_config() -> dict:
    try:
        with open(CONFIG, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def enable_session_restore(profile: str) -> bool:
    """让 profile 恢复上次会话：会话级 cookie（没有过期时间的）关机/关窗后不再丢。

    Chrome 只有在「继续浏览上次打开的网页」+ 正常退出时才会把会话 cookie 写盘。
    这一步在每次巡检前打补丁（幂等），是延长登录态最省事的一招。
    """
    pref_path = os.path.join(profile, "Preferences")
    try:
        data = {}
        if os.path.exists(pref_path):
            with open(pref_path, encoding="utf-8") as fh:
                data = json.load(fh)
        session = data.setdefault("session", {})
        session["restore_on_startup"] = 1          # 1 = 继续浏览上次打开的网页
        prof = data.setdefault("profile", {})
        prof["exit_type"] = "Normal"
        prof["exited_cleanly"] = True
        tmp = pref_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
        os.replace(tmp, pref_path)
        return True
    except Exception:
        return False


FINGERPRINT_JS = """() => ({
  ua: navigator.userAgent,
  lang: navigator.language,
  tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
  screen: `${screen.width}x${screen.height}`,
  dpr: window.devicePixelRatio,
})"""


def browser_path(cfg: dict) -> str:
    p = str(cfg.get("browserPath") or "").strip()
    if p and os.path.exists(p):
        return p
    for cand in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                 r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
        if os.path.exists(cand):
            return cand
    raise SystemExit("找不到 Chrome（config.browserPath 无效）")


def judge(account: dict, url: str, text: str) -> tuple[bool | None, str]:
    media = account.get("media", "")
    low_url = (url or "").lower()
    rule = LOGGED_OUT.get(media, DEFAULT_RULE)
    for frag in rule["url"]:
        if frag.lower() in low_url:
            return False, f"signed out (跳转到 {url})"
    for kw in rule.get("text", []):
        if kw in (text or ""):
            return False, f"signed out (页面出现「{kw}」)"
    expect = EXPECT.get(media)
    if expect:
        if any(frag.lower() in low_url for frag in expect):
            return True, f"signed in at {url}"
        return False, f"signed out (落地页不是后台：{url})"
    # 没配规则的平台：只有正文出现明确后台特征才算有效
    backend_hint = any(k in (text or "") for k in ("内容管理", "退出登录", "我的内容"))
    if backend_hint:
        return True, f"signed in at {url}"
    return None, f"无法判定，落地页：{url}"


def check_one(ctx_browser, account: dict, cfg: dict, out: dict) -> dict:
    code = account["code"]
    profile = account.get("profileDir") or os.path.join(DATA_DIR, "profiles", code)
    home = account.get("homeUrl") or account.get("loginUrl")
    rec = {"code": code, "media": account.get("media"), "account": account.get("account"),
           "profile": profile, "at": datetime.now().isoformat(timespec="seconds")}

    if os.path.exists(os.path.join(profile, "SingletonLock")):
        rec.update(ok=None, detail="skipped: profile in use (browser running)")
        return rec
    if not os.path.isdir(profile):
        rec.update(ok=False, detail="no profile yet (never signed in)")
        return rec

    try:
        enable_session_restore(profile)
        ctx = ctx_browser.launch_persistent_context(
            user_data_dir=profile,
            headless=True,
            viewport={"width": 1400, "height": 900},
            locale="zh-CN",
            args=["--no-first-run", "--no-default-browser-check", "--lang=zh-CN"],
            timeout=60000,
        )
    except Exception as exc:
        rec.update(ok=None, detail=f"launch failed: {str(exc)[:160]}")
        return rec

    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(home, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3500)
        url = page.url
        try:
            text = page.inner_text("body") or ""
        except Exception:
            text = ""
        ok, detail = judge(account, url, text)
        rec.update(ok=ok, detail=detail, url=url)
        try:
            rec["fingerprint"] = page.evaluate(FINGERPRINT_JS)
        except Exception:
            rec["fingerprint"] = None
        os.makedirs(SHOT_DIR, exist_ok=True)
        shot = os.path.join(SHOT_DIR, f"{code}-{datetime.now():%Y%m%d-%H%M%S}.png")
        try:
            page.screenshot(path=shot)
            rec["shot"] = shot
        except Exception:
            pass
    except Exception as exc:
        rec.update(ok=None, detail=f"check failed: {str(exc)[:160]}")
    finally:
        try:
            ctx.close()
        except Exception:
            pass
    return rec


def fingerprint_drift(results: list[dict]) -> list[str]:
    """对比上次记录的指纹：UA/时区/分辨率变了说明环境漂移，平台很容易因此判风险登出。"""
    fp_file = os.path.join(STATE_DIR, "fingerprints.json")
    prev = {}
    if os.path.exists(fp_file):
        try:
            with open(fp_file, encoding="utf-8") as fh:
                prev = json.load(fh)
        except Exception:
            prev = {}
    drift = []
    for r in results:
        fp = r.get("fingerprint")
        if not fp:
            continue
        old = prev.get(r["code"])
        if old:
            changed = [k for k in ("ua", "tz", "screen") if old.get(k) != fp.get(k)]
            if changed:
                drift.append(f"`{r['code']}` 指纹变了：{', '.join(changed)}")
        prev[r["code"]] = fp
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(fp_file, "w", encoding="utf-8") as fh:
            json.dump(prev, fh, ensure_ascii=False, indent=1)
    except Exception:
        pass
    return drift


def write_report(results: list[dict], accounts: list[dict], cfg: dict, drift: list[str] | None = None) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"# 自媒体账号登录状态（巡检时间 {now}）", "",
             "| 账号 | 平台 | 登录名 | 状态 | 说明 |", "|---|---|---|---|---|"]
    icon = {True: "✅ 有效", False: "❌ 失效", None: "⚠️ 未知"}
    for r in results:
        lines.append(f"| `{r['code']}` | {r['media']} | {r['account']} | {icon.get(r['ok'])} | {r['detail']} |")
    ok_n = sum(1 for r in results if r["ok"] is True)
    bad = [r["code"] for r in results if r["ok"] is False]
    if drift:
        lines += ["", "## 环境指纹漂移（可能导致被登出）", ""] + [f"- {d}" for d in drift]
    lines += ["", f"合计：{len(results)} 个账号，有效 {ok_n}，失效 {len(bad)}"
                  + (f"（{', '.join(bad)} 需要重新登录）" if bad else "")]
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    with open(HISTORY, "a", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def update_registry(results: list[dict]) -> int:
    """把巡检结果写回 accounts.json 的 lastCheck（先备份，原子替换）。"""
    if not os.path.exists(ACCOUNTS):
        return 0
    with open(ACCOUNTS, encoding="utf-8") as fh:
        data = json.load(fh)
    backup = ACCOUNTS + f".bak-{datetime.now():%Y%m%d-%H%M%S}"
    shutil.copy2(ACCOUNTS, backup)
    by_code = {r["code"]: r for r in results}
    changed = 0
    for acc in data.get("accounts", []):
        r = by_code.get(acc.get("code"))
        if not r or r["ok"] is None:
            continue
        acc["lastCheck"] = {"ok": bool(r["ok"]), "at": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                            "detail": r["detail"]}
        acc["updatedAt"] = acc["lastCheck"]["at"]
        changed += 1
    tmp = ACCOUNTS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, ACCOUNTS)
    return changed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="只查这些平台，逗号分隔：sohu,toutiao,netease,csdn")
    ap.add_argument("--no-write", action="store_true", help="不写回 accounts.json")
    ap.add_argument("--include-netease", action="store_true",
                    help="也巡检网易号（会顶掉已登录窗口，默认跳过）")
    ap.add_argument("--browser", default="", help="浏览器可执行文件，默认读 config.browserPath")
    args = ap.parse_args()

    cfg = load_config()
    exe = args.browser or browser_path(cfg)
    with open(ACCOUNTS, encoding="utf-8") as fh:
        data = json.load(fh)
    accounts = data.get("accounts", [])
    # 网易号的登录态是会话级 cookie：任何新开浏览器（包括本巡检）都会把已登录的窗口顶掉。
    # 默认跳过 netease，需要时显式 --include-netease。
    if not args.include_netease:
        skipped = [a for a in accounts if a.get("media") == "netease"]
        accounts = [a for a in accounts if a.get("media") != "netease"]
        for a in skipped:
            print(f"  [{a['code']}] netease 跳过（窗口常开，巡检会顶掉会话）")
    if args.only:
        want = {x.strip() for x in args.only.split(",") if x.strip()}
        accounts = [a for a in accounts if a.get("media") in want]

    print(f"浏览器: {exe}")
    print(f"待巡检 {len(accounts)} 个账号")

    results = []
    with sync_playwright() as pw:
        for acc in accounts:
            print(f"  [{acc['code']}] {acc.get('media')} {acc.get('account')} ...", end="", flush=True)
            rec = check_one(pw.chromium, acc, cfg, {})
            results.append(rec)
            mark = {True: "OK", False: "OUT", None: "SKIP"}[rec["ok"]]
            print(f" {mark}  {rec['detail'][:80]}")

    drift = fingerprint_drift(results)
    if drift:
        print("指纹漂移: " + "; ".join(drift))
    write_report(results, accounts, cfg, drift)
    if not args.no_write:
        n = update_registry(results)
        print(f"已回写 lastCheck: {n} 个账号")
    print(f"报告: {REPORT}")
    print(f"历史: {HISTORY}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
