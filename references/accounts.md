# 账号体系、登录态与投放节奏

## 1. 账号从哪来

全部来自 **ego-publish 插件**（数据目录 `~/.dsh/ego-publish`）：

- 注册表：`accounts.json`（每个账号有 code / media / account / profileDir / lastLoginAt / lastCheck）
- 每个账号一个独立浏览器 profile：`profiles/<code>`（独立 cookie 罐、独立登录态）
- 代号约定：`a-*` 搜狐、`t-*` 头条、`b-*` CSDN、`c-*` 网易

新建账号：

```
egolite_account { op:"upsert", code:"a-9", media:"sohu", account:"<手机号>" }
egolite_account { op:"login",  code:"a-9" }     # 弹窗，人工扫码
```

> **注意**：`accounts.json` 由插件在内存里维护。**不要用脚本直接改这个文件**（实测会被插件用内存状态覆盖，导致账号"消失"）；要增删账号一律走 `egolite_account upsert/remove`。

## 2. 登录态能撑多久（实测）

| 平台 | 实测寿命 | 说明 |
|---|---|---|
| 搜狐号 | 约 2–3 周 | 10-30 登录，11-02 仍有效，11-18 失效；期间完全没活动 |
| 头条号 | 2 周以上 | 24 个号里 8 个头条号一直在线 |
| CSDN | 稳定 | 11-13 登录，11-18、11-23 巡检均有效 |
| 网易号 | **会话级** | 关浏览器即掉，只能窗口常开 |

结论：**定期使用本身就是续期**。每 2 天一轮的巡检 + 发布，足以让搜狐/头条/CSDN 保持在线；网易号必须单独处理。

## 3. 登录态巡检（脚本 + 定时任务）

```powershell
python scripts/check_logins.py                 # 全部账号（默认跳过 netease）
python scripts/check_logins.py --only sohu     # 只查某个平台
python scripts/check_logins.py --no-write      # 只看结果，不回写
```

它做四件事：

1. 用 `config.browserPath` 指定的浏览器（本机是 Chrome）逐个打开账号 profile；
2. 按 URL 判据判定是否登录（**必须落到发布后台 URL 才算有效**，只看正文关键词会假阳性——搜狐公开首页里就有「发布」二字）；
3. 把结果回写 `accounts.json` 的 `lastCheck`（先备份、原子替换）；
4. 生成报告 `_state/登录状态.md` + 历史 `_state/login-history.jsonl` + 每账号截图。

判据表：

| 平台 | 有效判据 |
|---|---|
| 搜狐 | URL 含 `contentManagement` |
| 头条 | `mp.toutiao.com/profile` / `/creator` |
| CSDN | `mp.csdn.net/mp_blog` / `/user` |
| 网易 | `mp.163.com/#/` 或 `subscribe_v4`，且不是 `login.html` |

定时任务（`schedule_create`）：每天 **09:30 / 20:30** 各跑一次，rrule：

```
DTSTART;TZID=Asia/Shanghai:20261124T093000
RRULE:FREQ=DAILY;BYHOUR=9,20;BYMINUTE=30
```

## 3.5 浏览器模式：登录/验证有头，发布可无头

| 场景 | 模式 | 说明 |
|---|---|---|
| `egolite_account login` 扫码 | **有头** | 必须让人看见二维码 |
| 登录态巡检 `check_logins.py` | **有头**（`headless=False`）| 与真实环境一致，避免平台把无头判为异常会话 |
| 页面核验 / 抓状态 | **有头** | `egolite_script`、`egolite_observe` |
| `egolite_publish` 提交 | 可临时 `headless:true` | 发完立刻 `headless:false` |

> 实测：2026-11-23 全局无头连发之后，11-24 09:30 巡检发现搜狐 `a-3`/`a-5`/`a-6` 三个号同时掉线，而同日头条 8 个号全部正常。无头不是唯一变量，但**不要把无头当成默认**。

## 4. 三条铁律（都踩过）

1. **账号 profile 只能用一个浏览器打开**。ego-publish 的 `browserPath` 指向 Chrome，就用 Chrome；换成 ego.exe 会覆盖 `Local State` 的加密密钥，已登录的号当场掉线。
2. **同一 profile 同时只能有一个实例**。脚本启动前查 `SingletonLock`，占用就退出（`profile_guard.py` 已实现）。
3. **巡检与 GEO 检测不要同时跑**。两个浏览器 + 多标签页会把机器压到 Chrome 起不来（`GPU process exited`）。

## 5. 投放节奏与额度

- 每账号每天 **5 篇 = 3 篇企业案例 + 2 篇科普**
- 8 组账号满额：**24 篇企业案例 + 16 篇科普 = 40 篇/天**，每篇发三平台 → **120 次发布/天**
- 一篇稿子 → 搜狐 + 头条 + CSDN 各一次（每平台一个账号）
- **同账号两次发布间隔 45–150 分钟**（插件 `publishIntervalMinMinutes: 45`，建议不要调小）
- 所以 5 篇要摊到 **4–12 小时**，不能一口气发完
- 8 组账号（a-1..a-8 / t-1..t-8 / b-1..b-8）并行 = **24 案例 + 16 科普 = 40 篇/天**（120 次发布），瓶颈在写稿速度

排班示例（单组）：

| 时间 | 动作 |
|---|---|
| 09:30 | 巡检 + 第 1 篇（案例）|
| 10:30 | 第 2 篇（案例）|
| 11:30 | 第 3 篇（案例）|
| 14:00 | 第 4 篇（科普）|
| 15:30 | 第 5 篇（科普）|

> 单组满额 = 3 案例 + 2 科普；8 组同时按这张表跑，就是 24 案例 + 16 科普/天。

## 6. 台账与状态文件

| 文件 | 内容 |
|---|---|
| `_state/publish-ledger.jsonl` | 每次发布：时间/编号/企业/域名/类型(案例\|科普)/平台/账号/状态/链接 |
| `_state/login-history.jsonl` | 每次巡检：账号/平台/是否有效/落地页/时间 |
| `_state/登录状态.md` | 巡检汇总表（人看） |
| `_state/login-shots/` | 巡检截图 |
| `_geo/check-<日期>.xlsx` | 检测副本（含逐家命中结果） |
| `案例截图/<域名>/` | GEO 命中证据 |

## 7. 代理策略

- 本批账号全部**直连本机 IP**，不要中途挂代理（换 IP = 异地登录，必掉线）
- 真要隔离，一次性绑好再重登一次，别在跑批期间切换
