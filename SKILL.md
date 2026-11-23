---
name: geo-wangzhi-skill
description: 中文域名（.网址）GEO 案例流水线：读 Excel 企业表 → 用 AnySearch 补料并撰写约 1000 字企业案例稿（每篇必配一篇中文域名科普稿，案例:科普=3:2）→ 用 ego-publish 插件把每篇稿子同时发到搜狐号/头条号/CSDN（每篇在每个平台只落一个账号，账号按「每号每天 3 案例 + 2 科普」轮转）→ 间隔 2 天用 geo-shaicha 在豆包/DeepSeek/千问/元宝逐家提问「XX的官网是什么？」→ 命中 `.网址` 即截图并把「6.GEO案例」与「7.GEO完成时间」写回表格，未命中进入下一轮，直到表内全部企业至少一个平台命中。Use when the user asks 批量做 .网址 GEO 案例、给企业表写稿并发自媒体、检测 AI 回答里是否出现中文域名、按账号额度批量投放并回写表格。
metadata:
  version: "1.1.0"
  date: "2026-11-23"
  based_on: "2026-11 实跑 8 篇稿件 / 13 次发布 / 21 家 GEO 检测（命中 2 家，均元宝）"
---

# 中文域名 GEO 案例流水线

把一张企业表跑成「AI 能查到 `.网址`」的证据库：写稿 → 三平台发布 → 隔 2 天四平台检测 → 命中回写 → 循环到全表完成。

## 什么时候用

- 用户给一张含「注册域名 / 企业名称 / 企业资料」的 Excel，要求批量做 `.网址` 的 GEO 案例
- 要求「写完发到搜狐/头条/CSDN」「每号每天 5 篇（3 案例 + 2 科普）」「一稿发多个平台」
- 要求「检测豆包/DeepSeek/千问/元宝里有没有出现 `.网址`」并把结果回写表格
- 要求「没命中的隔两天再查，直到全部命中」

## 四条不可让步的边界

1. **完成判定只看表格「6.GEO案例」列有没有值**；命中平台写进该列，完成时间写「7.GEO完成时间」列（格式 `MM.DD`）。其他列不改。
2. **命中必须与本行域名等值**（允许豆包把 `.` 渲染成 `。`）；答成别家域名不算命中。
3. **一篇文章在同一个平台只发一个账号**；一篇稿子要分别发到搜狐号、头条号、CSDN 三个平台。
4. **不伪造数据、不伪造网站功能**；官网启用口径按用户统一确认（表中企业视为已启用对应 `.网址`）。AI 生成内容在头条号必须如实勾选「作品声明 = 引用AI」。

## 端到端流程

| # | 阶段 | 工具 | 通过标准 |
|---|---|---|---|
| 0 | 预检 | `scripts/check_logins.py` | 目标平台账号登录态有效；ego-browser 可用 |
| 1 | 读表 | openpyxl 只读 | 表头核对；取「6.GEO案例」为空的行 |
| 2 | 补料 | AnySearch（`anysearch_fill.py --company`） | 每篇有事实来源，不凭常识编 |
| 3 | 写案例稿 | 本 skill 规则 + `draft_check.py` | H1/H2/H7 全绿；900–1150 字；标题≤30 字 |
| 3b | 配科普稿 | `kepu_plan.py` 发方向 + `kepu_check.py` | K1–K6 全绿；900–1150 字；标题含「中文域名」+价值用语 |
| 4 | 发布 | `egolite_publish`（flows 见 `scripts/flows/`） | 三平台各自成功；同账号间隔 ≥45 分钟 |
| 5 | 记账 | `_state/publish-ledger.jsonl` | 时间/编号/平台/账号/状态 |
| 6 | GEO 检测 | `geo-shaicha-skill` + `scripts/geo_bridge.py` | 检测副本 21 家/批；命中出截图 |
| 7 | 回写 | `scripts/geo_bridge.py writeback` | 6.GEO案例 + 7.GEO完成时间 写入，备份先行 |

### 阶段 0：预检

```powershell
python scripts/check_logins.py            # 巡检全部账号（默认跳过网易号）
python scripts/check_logins.py --only sohu,toutiao,csdn
```

- 输出：每账号 OK / OUT / SKIP，回写 `accounts.json` 的 `lastCheck`，报告写 `_state/登录状态.md`
- 有 OUT → 让用户扫码：`egolite_account {op:"login", code:"<代号>"}`
- **巡检不要与 GEO 检测同时跑**（两个浏览器抢资源，Chrome 会 `GPU process exited` / `ERR_NETWORK_IO_SUSPENDED`）

### 阶段 1：读表

表结构（实测版）：

| 列 | 用途 |
|---|---|
| `编号` | 主键，回写定位用 |
| `1.注册域名` | 如 `椰林山`、`迈凯伦.网址`；缺失 `.网址` 时检测阶段自动补 |
| `2.企业名称` | 工商全称，写稿事实主体 |
| `3.简称` | 可选，缺省由脚本推导 |
| `4.企业资料` | 业务事实来源；空则用 AnySearch 补 |
| `5.新闻链接` | 已发布的自媒体链接（有值 = 可跳过写稿直接检测） |
| `6.GEO案例` | **完成标记**：`已完成（元宝）` 这类 |
| `7.GEO完成时间` | `MM.DD`；历史数据统一填 `10.30`，新命中填当天 |

分段：`6.GEO案例` 非空=已完成；为空且有 `5.新闻链接`=待检测；两者皆空=待写待发。

### 阶段 2–3：写稿（**批量法，5 篇一批**）

> 实测：一篇一跑一改要 15–25 分钟；**5 篇一批 + 集中过门禁只要约 7 分钟**（单篇 ~1.5 分钟）。
> 完整红线清单见 `references/writing.md`。

流程：一次选 5 家（3 案例 + 2 科普）→ 一次补料 → 一次写 5 篇 → 一次跑门禁 → 一次集中修。

写作红线（写的时候就避开，别等门禁）：

- 案例稿：标题 ≤30 字含企业名；首段含「全称 + 官网已启用 + 完整域名」且 **≥100 字 / ≥2 句**；6–7 段、每段 120–160 字；禁用「成立于 / 经营范围 / 注册资本 / 最新 / 首选 / 领先」；只出现 `.网址`
- 科普稿：标题含「中文域名」+ 价值用语；**≥3 处可量化表述**（要写成 `2010 年`、`30%`、`三成` 这种能被识别的形态）；不点名企业；只写正面（「吃亏 / 劣势 / 短板」会被 K1 拦）

规则与门禁见 `fabu-deepseek-harness`（本 skill 复用它的脚本），本 skill 额外固定：

- **案例稿标题**：必须含企业名称（全称版 ≤30 字用全称，否则用资料里已有的简称）；标题总长 ≤30 字
- **首段**：企业全称 + 「官网已启用」+ 完整域名，逐字出现；该段 ≥100 字且 ≥2 句（一句公告独占一段会被 H1f 判失败）
- **禁用词**：`成立于`、`经营范围`、`注册资本`、`最新`、`首选`、`领先` 等（`draft_check.py` 的 BANNED 列表）
- **科普稿**：6 个方向轮换，标题必须含「中文域名」+ 价值用语（有用/价值/有没有用…），≤30 字，≥3 处可量化表述，不写企业名
- 案例 : 科普 = **3 : 2**（用户口径），不要求严格 1:1 配对

```powershell
python <fabu>/scripts/draft_check.py --dir <项目文件夹>
python <fabu>/scripts/kepu_check.py --dir <项目文件夹>
python <fabu>/scripts/style_check.py --dir <项目文件夹>
```

### 阶段 4：发布（三平台）

账号与节奏：

- 账号池来自 ego-publish 注册表，代号：搜狐 `a-*`、头条 `t-*`、CSDN `b-*`、网易 `c-*`
- 一组 = `a-N / t-N / b-N`（同编号的三个平台账号）
- **每号每天 5 篇 = 3 篇企业案例 + 2 篇科普**
- 8 组（8 个搜狐号 + 8 个头条号 + 8 个 CSDN 号，共 24 个账号）满额日产能：

| 口径 | 数量 |
|---|---|
| 企业案例 | **24 篇/天**（8 组 × 3）|
| 科普 | **16 篇/天**（8 组 × 2）|
| 稿件合计 | **40 篇/天** |
| 发布次数 | **120 次/天**（每篇发搜狐+头条+CSDN 各一次）|

- **同账号两次发布间隔 45–150 分钟**（插件 `publishIntervalMinMinutes`），所以一个号的 5 篇要摊到 4–12 小时，不能连发
- 真实瓶颈是**写稿**：40 篇/天需要 40 篇 900–1150 字的合规稿，不是发布本身

```jsonc
// 搜狐（内置 flow 可用）
{ "accountCode":"a-2", "flow":"sohu__publish-article",
  "params":{"title":"…","body":"…"}, "dryRun":false }

// 头条（用本 skill 的 flows/toutiao__publish-article.json 覆盖内置版）
{ "accountCode":"t-2", "flow":"toutiao__publish-article",
  "params":{"title":"…","body":"…"}, "dryRun":false }

// CSDN（暂缓：见 references/platforms.md 的已知问题）
```

**成功判据以作品列表为准**，不以 URL 跳转为准：头条发布成功后常停在编辑页。

**头条防重复（v7 已修）**：`scripts/flows/toutiao__publish-article.json` 的提交步改成 **eval 单次 DOM 点击 + `__ksClicked` 标记**。旧版用 `click` 动作时，弹层关闭后引擎会重试一次，导致同一篇发两条（实测在 `t-2`、`t-3` 各踩过一次）。

### 阶段 6：GEO 检测（隔 2 天）

```powershell
# 1) 生成检测副本（只含未完成的行）
python scripts/geo_bridge.py make-check --segment B --out _geo/check-<日期>.xlsx   # B=已有新闻链接
python scripts/geo_bridge.py make-check --out _geo/check-all.xlsx                  # 全部未完成

# 2) 准备 ego 空间（p1 豆包 p2 DeepSeek p3 千问 p4 元宝）
& "<ego lite>\Application\<版本>\ego-browser.exe" nodejs -e "await import('file:///<abs>/scripts/setup_space.mjs')"

# 3) 跑检测（spaceId 用上一步打印的值）
python <geo-shaicha>/scripts/run.py --xlsx _geo/check-<日期>.xlsx --sheet Sheet1 `
    --space <spaceId> --outdir 案例截图 `
    --platforms doubao,deepseek,qianwen,yuanbao

# 4) 回写命中
python scripts/geo_bridge.py writeback --checked _geo/check-<日期>.xlsx --dry-run
python scripts/geo_bridge.py writeback --checked _geo/check-<日期>.xlsx
```

- 21 家约 40–70 分钟；单家 2–4 分钟（四平台 × 两问 + 15–35 秒限速）
- 命中截图落 `案例截图/<域名>/<平台>-<全称|简称>.png`
- **每次跑检测前必须重开 space**：ego lite 升级或浏览器关闭后旧 spaceId 全部失效（`taskSpace` 报错）

### 阶段 7：回写与循环

- 只写两列：`6.GEO案例`（`已完成（平台）`）、`7.GEO完成时间`（`MM.DD`）
- 写前自动备份 `最终数据（最新）.bak-<时间戳>.xlsx`，失败可回滚
- 未命中 → 留空 → 2 天后下一轮再查；连续 6 轮未命中 → 出清单交用户决定（不自动判死）

## 实测数据（用来校准预期）

| 指标 | 实测值 |
|---|---|
| 已发案例稿 | 5 篇（椰林山、迈凯伦、爱阁尔/claudia、聚丰/绿食安、新维合众/花伞）|
| 已发科普稿 | 4 篇（方向 1/2/3/4/5 已用到 4 个）|
| 发布次数 | 13 次（搜狐 4、头条 7、CSDN 1、其中头条 2 条重复）|
| 平台审核结果 | **0 篇被拒**（搜狐/头条/CSDN 全部正常发布）|
| 头条阅读量（冷启动）| 消费类 541、工业类 20–33、科普 10 |
| 单篇发布耗时 | 搜狐 60–90 s；头条 40–120 s；CSDN 2–5 min（分段输入）|
| GEO 检测命中率 | 21 家已发过稿的企业，**2 家命中（9.5%），全部是元宝** |
| 单家检测耗时 | 2–4 分钟 |
| 命中平台分布 | 元宝 2 / 豆包 0 / DeepSeek 0 / 千问 0 |

**结论**：元宝最容易捞到 `.网址`；单平台单篇很难被引用，命中主要靠多渠道 × 多篇累积。

## 常见故障与处置（都是实跑踩出来的）

| 现象 | 原因 | 处置 |
|---|---|---|
| `taskSpace` 报错 | spaceId 失效（ego lite 升级/浏览器关闭） | 重跑 `setup_space.mjs` 拿新 id |
| `ego-browser` 路径不存在 | ego lite 自动升级，路径带版本号 | 用 `scripts` 里的动态查找（glob `Application\*\ego-browser.exe`）|
| `C:\tmp\aidv_task.json` 不存在 | geo 的 worker 写死 `/tmp` | 已改为 `os.tmpdir()`（本 skill 假定该补丁已打）|
| 头条点「确认发布」无反应 | 缺「作品声明」，或标题被草稿重渲染清空 | 勾「引用AI」；标题用原生 setter 兜底写入并回读 |
| 头条发布成功但 URL 不变 | 平台行为 | 以作品列表出现标题为准；flow 里该步设为 optional |
| **头条同一篇发了两条** | 旧版 click 动作在弹层关闭后重试 | 用 v7 flow（eval 单次点击 + 标记）；已重复的按用户要求不删 |
| CSDN 正文 0 字 | 整段 type 卡死 CKEditor | 按段落逐段 type，每段间隔 ~300 ms |
| CSDN 点「发布博客」无反应 | 缺文章标签 / 该号额外必填项 | 先加标签；仍不行则暂缓该号（当前策略：CSDN 暂不发）|
| Chrome `GPU process exited` | 同时开太多浏览器 | 关掉闲置 session；巡检与检测错开 |
| `ERR_NETWORK_IO_SUSPENDED` | 浏览器被挂起 | 关闭该账号 session 后重开再发 |
| 网易号「明明登录了却未登录」 | 会话级 cookie，关浏览器即丢 | 网易号只能用「窗口常开 + 同会话发布」；巡检默认跳过 |

## 迁移到另一台电脑（清单）

1. **装 DeepSeek Harness**，并确保这两个技能可用：`fabu-deepseek-harness`（写稿门禁脚本）、`geo-shaicha-skill`（四平台检测脚本）
2. **装 ego-publish 插件**（账号体系与发布能力都来自它）+ ego lite 浏览器
3. **注册账号**：`egolite_account {op:"upsert", code:"a-1", media:"sohu", account:"<手机号>"}`，每个账号扫码登录一次
4. **放表**：把 Excel 放到固定路径，改 `scripts/geo_bridge.py` 顶部 `MASTER` / `SHEET`
5. **跑巡检**：`python scripts/check_logins.py`，确认所有账号 OK
6. **建定时任务**：每日 09:30 / 20:30 跑巡检（`schedule_create`，rrule `FREQ=DAILY;BYHOUR=9,20;BYMINUTE=30`）
7. **首发一篇试跑**：dry run → 真发 → 作品列表确认

## 参考文件

| 文件 | 内容 |
|---|---|
| `references/writing.md` | **写作红线清单 + 批量法**（把单篇压到 ~1.5 分钟）|
| `references/platforms.md` | 三平台发布细节、选择器、已知坑与 flow 改法 |
| `references/geo-check.md` | GEO 检测全流程、Windows 适配、命中判定与回写 |
| `references/accounts.md` | 账号体系、登录态机制与巡检、额度与节奏 |
| `references/runbook.md` | 每日 / 每轮操作手册（可直接照着执行） |
