# 操作手册（照着做即可）

本手册假设：

- 表格：`<MASTER>`（默认 `C:\Users\Administrator\Desktop\增值服务\最终数据（最新）.xlsx`，工作表 `最终数据（11.10）`）
- 技能目录：`<SKILL>`（本 skill 根目录）
- geo 检测脚本：`<GEO>`（`geo-shaicha-skill/scripts`）
- 写稿门禁脚本：`<FABU>`（`fabu-deepseek-harness/scripts`）
- Python：`<PY>`（DSH 自带或 media-publish 自带的 python.exe）

---

## A. 每日开机检查（3 分钟）

```powershell
# 1) 登录态
& <PY> <SKILL>\scripts\check_logins.py
#    OUT 的账号 -> egolite_account {op:"login", code:"<代号>"} 请用户扫码

# 2) 看表：还有多少未完成
& <PY> -c "import openpyxl;ws=openpyxl.load_workbook(r'<MASTER>',data_only=True)['最终数据（11.10）'];h=[c.value for c in ws[1]];g=h.index('6.GEO案例')+1;print('未完成', sum(1 for r in range(2,ws.max_row+1) if not str(ws.cell(r,g).value or '').strip()))"

# 3) 看台账：今天已发几篇、各账号间隔是否够
Get-Content <状态目录>\_state\publish-ledger.jsonl -Tail 10
```

## B. 写一批稿（5 篇约 7 分钟，红线清单见 references/writing.md）

1. **一次取 5 行**：3 家写案例 + 2 篇科普；优先「4.企业资料」≥120 字的行，避开已在发/已发的编号
   **先过滤 `6.GEO案例` 非空的行**——已完成的 GEO 案例不再发稿（硬规则）
2. **补料**（资料为空或过短时）：
   ```powershell
   & <PY> <FABU>\anysearch_fill.py --company "<企业全称>" --max_results 6
   ```
3. **写案例稿** `NN-<简称>-稿件.txt`：
   - 标题 ≤30 字，含企业名称（全称版 ≤30 用全称，否则用资料里已有的简称）
   - 第 1 段：企业全称 + 「官网已启用」+ 完整域名（如 `某某.网址`），逐字出现；该段 ≥100 字且 ≥2 句
   - 正文 900–1150 中文字；不写 `成立于/经营范围/注册资本/最新/首选/领先`
   - 只出现 `.网址` 后缀，不举例其他后缀
4. **配科普稿**（每 3 篇案例配 2 篇科普）：
   ```powershell
   & <PY> <FABU>\kepu_plan.py plan --count 2 --out plan.json   # 拿方向号
   ```
   标题必须含「中文域名」+ 价值用语（有用/有没有用/价值…），≤30 字；≥3 处可量化表述；不写企业名
5. **过门禁**：
   ```powershell
   & <PY> <FABU>\draft_check.py --dir <批次目录>
   & <PY> <FABU>\kepu_check.py  --dir <批次目录>
   & <PY> <FABU>\style_check.py --dir <批次目录>
   ```
   全绿才进发布；单篇实体识别不准时显式传参：
   `draft_check.py <file> --full "<全称>" --short "<简称>" --domain "<域名>.网址"`

## C. 发一篇到三平台

```jsonc
// 1) 彩排（必做）
{ "accountCode":"a-2", "flow":"sohu__publish-article",
  "params":{"title":"…","body":"…"} }          // dryRun 默认 true

// 2) 真发（搜狐）
{ "accountCode":"a-2", "flow":"sohu__publish-article",
  "params":{"title":"…","body":"…"}, "dryRun":false }

// 3) 真发（头条）—— 必须先装好本 skill 的 flow
{ "accountCode":"t-2", "flow":"toutiao__publish-article",
  "params":{"title":"…","body":"…"}, "dryRun":false }
```

安装/覆盖 flow：

```
egolite_flow { op:"save", overwrite:true,
  spec: <scripts/flows/toutiao__publish-article.json 的内容> }
```

发布后**立刻核验**（不要只看工具返回值）：

- 搜狐：`https://mp.sohu.com/mpfe/v4/contentManagement/first/page` 列表里有该标题
- 头条：`https://mp.toutiao.com/profile_v4/graphic/articles` 列表里有该标题

核验通过再记账：

```jsonl
{"at":"2026-11-23T13:32:00+08:00","no":4,"company":"…","domain":"….网址","kind":"案例","platform":"头条号","account":"t-2","status":"已发布","link":null}
```

## D. 隔 2 天做一轮 GEO 检测

```powershell
# 1) 检测副本
& <PY> <SKILL>\scripts\geo_bridge.py make-check --segment B --out <状态目录>\_geo\check-<日期>.xlsx

# 2) 重开 ego 空间（每次都要）
& "<ego lite>\Application\<版本>\ego-browser.exe" nodejs -e "await import('file:///<SKILL>/scripts/setup_space.mjs')"

# 3) 跑检测（spaceId 用上一步输出的值）
& <PY> <GEO>\run.py --xlsx <状态目录>\_geo\check-<日期>.xlsx --sheet Sheet1 `
    --space <spaceId> --outdir <状态目录>\案例截图 `
    --platforms doubao,deepseek,qianwen,yuanbao

# 4) 回写
& <PY> <SKILL>\scripts\geo_bridge.py writeback --checked <状态目录>\_geo\check-<日期>.xlsx --dry-run
& <PY> <SKILL>\scripts\geo_bridge.py writeback --checked <状态目录>\_geo\check-<日期>.xlsx
```

跑完检查：

- `_geo/check-<日期>.xlsx` 的「命中平台」列有值的行 = 本轮命中
- 主表对应行的 `6.GEO案例` 应变成 `已完成（元宝）` 之类，`7.GEO完成时间` 是当天 `MM.DD`

## E. 每周维护

| 检查项 | 动作 |
|---|---|
| 未完成企业数 | 评估按当前产能还要几天 |
| 连续 6 轮未命中的企业 | 单独出清单，交用户决定（加渠道 / 换角度 / 放弃） |
| 账号掉线频率 | 超过每周 2 次 → 考虑固定代理（一次性绑好再重登） |
| 表结构 | 若用户增删列，同步改 `geo_bridge.py` 顶部的列名映射 |
| ego lite 升级 | 重跑一次 `setup_space.mjs`，确认 geo 脚本仍能找到 ego-browser |

## F. 交付话术（每轮结束给用户）

```
本轮：新发 N 篇（案例 X / 科普 Y），三平台共 M 次发布
检测：完成 K 家，新命中 Z 家（平台分布：…）
累计：表内 368 家，已完成 A 家，剩余 B 家
待办：失效账号（…）、审核中待回填（…）、未命中超 6 轮（…）
```
