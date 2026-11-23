# geo-wangzhi-skill

中文域名（`.网址`）**GEO 案例流水线**的完整 skill：写稿 → 三平台发布 → 隔 2 天四平台检测 → 命中回写表格 → 循环到全表完成。

> 版本 1.1.0（2026-11-23）· 基于实跑数据沉淀：8 篇稿件 / 13 次发布（0 篇被拒）/ 21 家 GEO 检测（命中 2 家，均为元宝）

## 这个 skill 解决什么

一张企业表（368 行），每家要证明"AI 能查到它的 `.网址`"。做法是：

1. 给每家企业写一篇约 1000 字的案例稿（含企业全称 + 官网启用 + 完整域名）
2. 每 3 篇案例配 2 篇中文域名科普稿（按 6 个方向轮换）
3. 每篇稿子同时发到 **搜狐号 / 头条号 / CSDN**（每平台一个账号，不重复投）
4. 隔 2 天用四平台（豆包/DeepSeek/千问/元宝）逐家提问，命中即截图
5. 命中写回表格「6.GEO案例」+「7.GEO完成时间」，未命中 2 天后再查
6. 直到表内每家企业至少一个平台命中

**满额产能**：8 组账号（搜狐/头条/CSDN 各 8 个）× 每号每天 5 篇 = **24 篇企业案例 + 16 篇科普 = 40 篇/天**，每篇发三平台 = **120 次发布/天**。

## 依赖（迁移时必须先装）

| 依赖 | 用途 |
|---|---|
| `fabu-deepseek-harness` skill | 写稿门禁：`draft_check.py` / `kepu_check.py` / `style_check.py` / `kepu_plan.py` / `anysearch_fill.py` |
| `geo-shaicha-skill` | 四平台检测：`run.py` / `worker_chat.js` / `worker_yuanbao.js` / `media_map.py` |
| `ego-publish` 插件 + ego lite | 账号体系（独立 profile）与三平台发布能力 |
| Python + openpyxl | 表格读写 |
| AnySearch | 企业资料补全与行业素材 |

## 用哪个 Python

| 脚本 | 解释器 | 原因 |
|---|---|---|
| `check_logins.py`、`publish_netease.py` | 带 **playwright** 的 python（本机 `C:\Users\Administrator\.dsh\media-publish\python\Scripts\python.exe`）| 要驱动浏览器 |
| `geo_bridge.py`、`add_geo_time_col.py` | 带 **openpyxl** 的 python（DSH 自带即可）| 只读写 Excel |
| `setup_space.mjs` | `ego-browser.exe nodejs -e "await import(...)"` | ego lite 内嵌 Node |

## 目录结构

```
geo-wangzhi-skill/
├── SKILL.md                     # 主文档：边界、端到端流程、状态机、故障表、迁移清单
├── README.md                    # 本文件
├── scripts/
│   ├── check_logins.py          # 登录态巡检（跳过网易号，回写 lastCheck，出报告）
│   ├── geo_bridge.py            # 主表 ↔ 检测表：make-check / writeback（含完成时间列）
│   ├── profile_guard.py         # 账号 profile 备份/回滚（防掉登录）
│   ├── publish_netease.py       # 网易号独立发布脚本（窗口常开模式）
│   ├── add_geo_time_col.py      # 首次部署：给表加「7.GEO完成时间」列
│   ├── setup_space.mjs          # 每次检测前重开 ego 空间（四平台标签页）
│   └── flows/                   # 覆盖内置版的发布流程
│       ├── toutiao__publish-article.json   # 无封面 + 引用AI + 落地页可选
│       ├── csdn__publish-article.json      # CKEditor 分段输入 + 标签
│       └── netease__publish-article.json   # 新版页面 + 封面自动
└── references/
    ├── platforms.md             # 三平台发布细节、选择器、已知坑
    ├── geo-check.md             # 检测流程、Windows 适配、判定与回写
    ├── accounts.md              # 账号体系、登录态寿命、额度与排班
    └── runbook.md               # 每日/每轮操作手册（可直接照做）
```

## 最快上手（迁移到新电脑）

```powershell
# 1) 环境变量（可选，默认路径见各脚本顶部）
$env:GEO_XLSX      = "D:\work\最终数据.xlsx"
$env:GEO_SHEET     = "最终数据（11.10）"
$env:GEO_STATE_DIR = "D:\work\_state"

# 2) 首次：给表加完成时间列（幂等）
python <SKILL>\scripts\add_geo_time_col.py

# 3) 登录态巡检
python <SKILL>\scripts\check_logins.py

# 4) 覆盖头条发布流程（内置版会失败）
#    egolite_flow { op:"save", overwrite:true, spec: <scripts/flows/toutiao__publish-article.json> }

# 5) 写稿 → 发三平台 → 隔 2 天检测 → 回写（详见 references/runbook.md）
```

## 三条最容易踩的坑

1. **头条**：必须选「无封面」+ 勾「作品声明 = 引用AI」，发布成功以**作品列表**为准（URL 常不跳转），否则会重复发。
2. **CSDN**：正文必须**分段输入**（整段 type 会卡死编辑器）；必须加文章标签；当前有账号点发布无反应，策略是暂缓。
3. **GEO 检测**：每次跑之前必须**重开 ego 空间**（ego lite 一升级或浏览器一关，旧 spaceId 全失效）；巡检与检测不要同时跑。

## 数据与口径

- 完成判定：表格 `6.GEO案例` 有值即完成（如 `已完成（元宝）`）
- 完成时间：`7.GEO完成时间`，格式 `MM.DD`；历史数据统一 `10.30`，新命中写当天
- 命中判定：回答里出现**与本行域名等值**的 `.网址`（`.`/`。` 等价），子串不算
- 实测命中率：已发过稿的 21 家命中 2 家（9.5%），**全部由元宝命中**

## 版本记录

| 版本 | 日期 | 变化 |
|---|---|---|
| 1.0.0 | 2026-11-23 | 首次成文：三平台发布 + GEO 检测 + 回写 + 巡检定时化，沉淀 10 条实跑故障处置 |
| 1.1.1 | 2026-11-23 | 发布改为**无头浏览器**（降内存）；搜狐必须声明「含有AI生成内容」；记录搜狐 5/7 拒稿实测 |
| 1.1.0 | 2026-11-23 | 新增**批量写稿法**（单篇 15–25 分钟 → 约 1.5 分钟）+ 写作红线清单；头条 flow 升到 v7（eval 单次点击防重复）；补每日产能口径（24 案例 + 16 科普）与实测阅读数据 |
