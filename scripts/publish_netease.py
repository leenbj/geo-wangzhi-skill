#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""网易号自动发布脚本（Standalone，走 ego lite 的账号 profile + Playwright）。

为什么不用内置 flow：内置 netease__publish-article 的选择器已和 2026-11 的新版页面脱节
（标题框改成 textarea.netease-textarea，分类级联器 / 标签输入器都已移除）。本脚本直接用
稳定选择器 + 显式「封面=自动」。

用法：
  # 试跑（填完表单、选好封面、截图，不提交）
  python publish_netease.py --account c-1 --title "..." --body-file 稿件.txt

  # 真发
  python publish_netease.py --account c-1 --title "..." --body-file 稿件.txt --publish

  # 从表格行取标题/正文（预留）
  python publish_netease.py --account c-1 --job job.json --publish

产物：
  默认写到 <outdir>/<timestamp>-<account>/：截图若干 + result.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime

import profile_guard as guard
from playwright.sync_api import sync_playwright

EGO_CANDIDATES = [
    r"C:\Program Files\Citro Labs\ego lite\Application\ego.exe",
    r"C:\Program Files\Citro Labs\ego lite\Application\0.6.3.14\ego.exe",
]
DATA_DIR = os.path.expandvars(r"%USERPROFILE%\.dsh\ego-publish")
CONFIG = os.path.join(DATA_DIR, "config.json")


def find_browser() -> str:
    """账号 profile 是哪个浏览器建的，就得用哪个浏览器打开。

    ego-publish 的 config 里 browserPath 指向 Chrome 时，profile 就是 Chrome 格式；
    用 ego.exe 打开会认不出 cookie，表现为"明明登录过却是未登录"。
    """
    try:
        with open(CONFIG, encoding="utf-8") as fh:
            cfg = json.load(fh)
        path = str(cfg.get("browserPath") or "").strip()
        if path and os.path.exists(path):
            return path
    except Exception:
        pass
    for cand in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                 r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
        if os.path.exists(cand):
            return cand
    return find_ego()
PUBLISH_URL = "https://mp.163.com/subscribe_v4/index.html#/article-publish"
TITLE_SEL = "textarea.netease-textarea"
BODY_SEL = ".public-DraftEditor-content"


def find_ego() -> str:  # noqa: D401
    for p in EGO_CANDIDATES:
        if os.path.exists(p):
            return p
    raise SystemExit("找不到 ego.exe，请用 --ego 指定路径")


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def shot(page, outdir: str, name: str) -> str:
    path = os.path.join(outdir, f"{name}.png")
    try:
        page.screenshot(path=path, full_page=False)
    except Exception as exc:  # 截图失败不该中断发布
        log(f"截图失败 {name}: {exc}")
        return ""
    return path


def choose_cover_auto(page) -> str:
    """封面选「自动」。返回命中的选择器描述；失败返回 ''。"""
    strategies = [
        ("get_by_text", lambda: page.get_by_text("自动", exact=True).first),
        ("label-xpath", lambda: page.locator("xpath=//label[normalize-space(.)='自动']").first),
        ("text=自动", lambda: page.locator("text=自动").first),
    ]
    for name, factory in strategies:
        try:
            loc = factory()
            if loc.count() == 0:
                continue
            loc.click(timeout=5000)
            page.wait_for_timeout(300)
            return name
        except Exception as exc:
            log(f"封面策略 {name} 失败: {str(exc).splitlines()[0]}")
    return ""


def publish(args) -> dict:
    ego = args.ego or find_browser()
    profile = os.path.join(DATA_DIR, "profiles", args.account)
    if not os.path.isdir(profile):
        raise SystemExit(f"账号 profile 不存在: {profile}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = os.path.join(args.outdir, f"{stamp}-{args.account}")
    os.makedirs(outdir, exist_ok=True)
    result = {"account": args.account, "dryRun": not args.publish, "outdir": outdir,
              "shots": [], "url": None, "titleLen": len(args.title), "bodyLen": len(args.body)}

    # 登录态保护：先确认 profile 没被占用，再备份加密密钥与 cookie，万一这次启动把人踢下线就回滚
    if args.guard:
        if guard.locked(profile):
            raise SystemExit("该账号的浏览器正在运行（profile 被占用）。先 egolite_session close，或手动关掉窗口再跑。")
        result["backup"] = guard.backup(profile)
        log(f"已备份登录态文件: {result['backup']}")

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=profile,
            executable_path=ego,
            headless=False,
            viewport={"width": 1600, "height": 900},
            locale="zh-CN",
            args=["--no-first-run", "--no-default-browser-check", "--lang=zh-CN",
                  "--window-size=1600,900", "--disable-blink-features=AutomationControlled"],
        )
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.set_default_timeout(30000)

            log("打开网易号发布页")
            page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=90000)

            # 刚登录后偶发跳到账号保护页，重试一次
            if "login.html" in page.url:
                raise RuntimeError("这个 profile 现在是未登录状态（被踢下线或有别的浏览器写过它）。"
                                   "已回滚登录态备份；请先 egolite_account {op:login} 重新登录一次，之后用插件流程发布就不会再掉。")
            if "account-protect" in page.url:
                log("命中账号保护页，等 3 秒后重试")
                page.wait_for_timeout(3000)
                page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=90000)

            page.wait_for_selector(TITLE_SEL, timeout=90000)
            result["shots"].append(shot(page, outdir, "01-editor-open"))

            log("填标题")
            page.fill(TITLE_SEL, args.title)
            page.wait_for_selector(BODY_SEL, timeout=60000)
            log("填正文")
            page.click(BODY_SEL)
            try:
                page.keyboard.insert_text(args.body)
            except Exception:
                page.keyboard.type(args.body, delay=5)
            page.wait_for_timeout(800)

            cover_by = choose_cover_auto(page) if args.cover == "auto" else ""
            result["cover"] = cover_by or "not-clicked"
            log(f"封面: {'自动（命中 ' + cover_by + '）' if cover_by else '未选中，请人工确认'}")

            stats = page.evaluate(
                """() => {
                    const body = document.querySelector('.public-DraftEditor-content');
                    const title = document.querySelector('textarea.netease-textarea');
                    const counter = [...document.querySelectorAll('*')]
                        .filter(e => e.children.length === 0 && /^共\\s*\\d+\\s*字$/.test((e.innerText || '').trim()))
                        .map(e => e.innerText.trim());
                    return {
                        title: title ? title.value : null,
                        bodyLen: body ? (body.innerText || '').trim().length : 0,
                        counter: counter[0] || null,
                    };
                }"""
            )
            result.update(stats)
            if (stats.get("title") or "") != args.title:
                raise RuntimeError(f"标题没写进去：{stats.get('title')!r}")
            if (stats.get("bodyLen") or 0) < 250:
                raise RuntimeError(f"正文只有 {stats.get('bodyLen')} 字，网易号要求 250 字以上")

            result["shots"].append(shot(page, outdir, "02-filled"))

            if not args.publish:
                log("dry-run：表单已填好、封面已选，停在提交前")
                result["ok"] = True
                result["submitSkipped"] = True
                return result

            log("点发布")
            btn = page.get_by_role("button", name="发布", exact=True)
            if btn.count() == 0:
                btn = page.locator("button:has-text('发布')").last
            btn.click()
            page.wait_for_timeout(1500)

            # 可能的二次确认
            confirm = page.get_by_text("确认发布", exact=True)
            if confirm.count():
                confirm.first.click()
                page.wait_for_timeout(1000)

            url = ""
            for _ in range(30):
                url = page.url
                if "article-publish" not in url and "mp.163.com" not in url:
                    break
                if "发布成功" in (page.content() or ""):
                    break
                page.wait_for_timeout(1000)
            page.wait_for_timeout(1500)
            result["url"] = page.url
            result["shots"].append(shot(page, outdir, "03-after-submit"))
            result["ok"] = True
            log(f"提交后落地页: {page.url}")
            return result
        finally:
            try:
                ctx.close()
            except Exception:
                pass


def main() -> int:
    ap = argparse.ArgumentParser(description="网易号自动发布（ego lite profile + Playwright）")
    ap.add_argument("--account", default="c-1")
    ap.add_argument("--title", default="")
    ap.add_argument("--body", default="")
    ap.add_argument("--body-file", default="")
    ap.add_argument("--job", default="", help='{"title":..,"body":..} 或 {"titleFile":..,"bodyFile":..}')
    ap.add_argument("--cover", default="auto", choices=["auto", "none"])
    ap.add_argument("--publish", action="store_true", help="不加则 dry-run，只填表不提交")
    ap.add_argument("--no-guard", dest="guard", action="store_false", help="跳过 profile 备份/回滚")
    ap.add_argument("--ego", default="", help="浏览器可执行文件；默认读 ego-publish config 的 browserPath")
    ap.add_argument("--outdir", default=r"C:\Users\Administrator\Desktop\开发流程\publish-runs")
    args = ap.parse_args()

    if args.job:
        with open(args.job, encoding="utf-8") as fh:
            job = json.load(fh)
        args.title = args.title or job.get("title", "")
        args.body = args.body or job.get("body", "")
        if not args.body and job.get("bodyFile"):
            with open(job["bodyFile"], encoding="utf-8") as fh:
                args.body = fh.read()
    if not args.body and args.body_file:
        with open(args.body_file, encoding="utf-8") as fh:
            args.body = fh.read()
    args.body = (args.body or "").strip()
    if not args.title or not args.body:
        ap.error("需要 --title 与 --body/--body-file/--job")

    try:
        result = publish(args)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "trace": traceback.format_exc()[-1200:]},
                         ensure_ascii=False, indent=1))
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=1))
    with open(os.path.join(result["outdir"], "result.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
