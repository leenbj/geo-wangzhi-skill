# -*- coding: utf-8 -*-
"""账号 profile 保护：任何外部脚本碰账号 profile 之前先做这件事。

为什么需要：ego-publish 的账号 profile 是 Chrome 建的（config.browserPath 指 chrome.exe）。
Chrome 的 cookie 用 Local State 里的 os_crypt 密钥加密；换成 ego.exe / 别的 Chromium 去开同一个
目录，会把 Local State 改写，老 cookie 立刻解不开 —— 表现就是"明明登录过却要重新登录"。

本模块提供：
  backup(profile)  : 把 Local State / Network/Cookies 复制到 <profile>/_login_backup/
  restore(profile) : 用备份覆盖回去（登录页兜底，避免把人踢下线）
  locked(profile)  : 判断该 profile 是否正被浏览器占用（SingletonLock）

注意：Chrome 的 SingletonLock 是符号链接/文件，进程结束后可能残留；这里只做提示不做强制。
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime

FILES = ["Local State", os.path.join("Network", "Cookies"), os.path.join("Network", "Cookies-journal")]


def _paths(profile: str):
    return [(src, os.path.join(profile, "_login_backup", src)) for src in FILES]


def locked(profile: str) -> bool:
    return os.path.exists(os.path.join(profile, "SingletonLock"))


def backup(profile: str) -> str:
    dst_root = os.path.join(profile, "_login_backup")
    os.makedirs(dst_root, exist_ok=True)
    copied = []
    for src, dst in _paths(profile):
        full = os.path.join(profile, src)
        if os.path.exists(full):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(full, dst)
            copied.append(src)
    with open(os.path.join(dst_root, "STAMP.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"backup at {datetime.now():%Y-%m-%d %H:%M:%S}\nfiles: {copied}\n")
    return ",".join(copied)


def restore(profile: str) -> list[str]:
    restored = []
    for src, dst in _paths(profile):
        if os.path.exists(dst):
            target = os.path.join(profile, src)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(dst, target)
            restored.append(src)
    return restored
