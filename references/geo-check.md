# GEO 检测：四平台提问、命中判定、回写

检测能力来自 `geo-shaicha-skill`（四平台提问 + 浮层截图 + 等值判定）。本文件记录**在本机跑通它所需的全部适配**与回写口径。

## 1. 一次检测的完整步骤

```powershell
# ① 生成检测副本（只含未完成的行，列名规范成 域名/公司名称/公司简称）
python scripts/geo_bridge.py make-check --segment B --out _geo/check-<日期>.xlsx
#    B = 有「5.新闻链接」但「6.GEO案例」为空的行（已发过稿，可直接检测）
#    不加 --segment 则取全部未完成行

# ② 准备 ego 空间（每次都要重开，见第 3 节）
& "<ego lite>\Application\<版本>\ego-browser.exe" nodejs `
    -e "await import('file:///<skill 绝对路径>/scripts/setup_space.mjs')"
#    输出 spaceId（通常是 1），四个标签页分别是 豆包/DeepSeek/千问/元宝

# ③ 跑检测
python <geo-shaicha>\scripts\run.py `
    --xlsx _geo\check-<日期>.xlsx --sheet Sheet1 `
    --space <spaceId> --outdir 案例截图 `
    --platforms doubao,deepseek,qianwen,yuanbao

# ④ 回写（先 dry-run 看将改哪些格子）
python scripts/geo_bridge.py writeback --checked _geo/check-<日期>.xlsx --dry-run
python scripts/geo_bridge.py writeback --checked _geo/check-<日期>.xlsx
```

节奏：21 家 ≈ 40–70 分钟；单家 2–4 分钟（四平台 × 两问 + 平台间 15–35 秒限速）。

## 2. 提问与判定口径（不得变更）

1. 先问 `<企业全称>的官网是什么？`
2. **只有该平台没命中**，才在同一会话补问 `<企业简称>的官网是什么？`
3. 命中 = 回答正文出现**与本行域名等值**的 `.网址`；`.` 与 `。．·・` 等价，命中值统一归一成英文点
4. 子串不算命中（`春芳.网址` ≠ `中国春芳.网址`）
5. 命中即截图：只截「本次提问 + 本次回答」的浮层，不整页截
6. 至少一个平台命中 → 该企业完成

## 3. Windows 适配（必须打，否则第一行就崩）

| 问题 | 修法 |
|---|---|
| worker 写死 `/tmp/aidv_task.json` | 改成 `node:os` 的 `tmpdir()`（本 skill 的 `scripts/` 假定该补丁已打在 geo-shaicha 里） |
| `ego-browser` 不在 PATH | 动态 glob：`C:\Program Files\Citro Labs\ego lite\Application\*\ego-browser.exe` |
| ego lite 自动升级后旧路径失效 | 同上；**每次升级都要重开 space** |
| `taskSpace` 报错 | spaceId 失效（浏览器被关/升级），重跑 `setup_space.mjs` |
| 并发过高 → `GPU process exited` / `ERR_NETWORK_IO_SUSPENDED` | 巡检与检测错开；先关闲置 session |

`run.py` 里这两处补丁已内联，迁移时若重新安装 geo-shaicha，需要重新打（或直接把本 skill 的 `scripts/` 里逻辑照抄）。

## 4. 命中结果的形态

检测副本会被 run.py 写入这些列：

```
编号 | 域名 | 公司名称 | 公司简称 | 原始域名
     | 豆包 | DeepSeek | 千问 | 元宝 | 命中平台 | 截图 | 状态 | 引用来源 | 引用链接
```

- `命中平台`：`元宝` / `豆包、千问` 这种
- `截图`：`案例截图/<域名>/<平台>-<全称|简称>.png`，多张用 `；` 分隔
- `状态`：`已完成` / `失败`

## 5. 回写口径（只写两列）

`geo_bridge.py writeback` 只做两件事：

| 列 | 写入值 |
|---|---|
| `6.GEO案例` | `已完成（<命中平台>）`，如 `已完成（元宝）` |
| `7.GEO完成时间` | `MM.DD`（当天日期） |

- 只写「命中平台」非空的行；未命中的行**不动**（留空等下一轮）
- 同名企业合并：命中一家，同名行一起结案（可用 `--merge-same-name`，默认开）
- 写前自动备份 `最终数据（最新）.bak-<时间戳>.xlsx`
- 已 `已完成` 的行不会被覆盖

## 6. 实测命中率与预期校准

2026-11 实跑：**21 家「已发过稿、未完成」的企业，命中 2 家（9.5%），全部由元宝命中**，豆包/DeepSeek/千问 0。

结论：

- 元宝对 `.网址` 的抓取与复述最强，是最主要的验收平台
- 单平台单篇很难被 AI 引用；命中靠多渠道 × 多篇累积
- 不要把「发了就一定命中」当预期，2 天一轮、多轮复检是常态

## 7. 检测失败的处理

| 现象 | 处理 |
|---|---|
| 单家报错（`taskSpace`、超时） | 该行状态记为「失败」，重跑同一命令会自动重试（只跳过「已完成」） |
| 大面积失败 | 先检查 space 是否失效、ego lite 是否刚升级 |
| 平台要求登录 | 在 ego lite 里登录四平台（豆包/DeepSeek/千问/元宝），登录态可复用很久 |
| 截图缺失 | 不影响判定，但证据不全；命中行建议重跑一次补图 |


## 8. geo-shaicha 的 Windows 补丁（重装后需重打）

`run.py`：把写死的临时路径与 ego-browser 路径改掉。

```python
# 顶部
import glob, shutil, tempfile

def _find_ego_browser():
    env = os.environ.get("EGO_BROWSER")
    if env and os.path.exists(env):
        return env
    base = r"C:\Program Files\Citro Labs\ego lite\Application"
    cands = sorted(glob.glob(os.path.join(base, "*", "ego-browser.exe")), reverse=True)
    if cands:
        return cands[0]
    return shutil.which("ego-browser") or "ego-browser"

EGO_BROWSER = _find_ego_browser()

# run_worker 里
p = subprocess.run([EGO_BROWSER, "nodejs"], stdin=src, capture_output=True, text=True,
                   encoding="utf-8", errors="replace", timeout=1200)

# 临时文件
tmp_chat = os.path.join(tempfile.gettempdir(), "aidv_task.json")
tmp_yb   = os.path.join(tempfile.gettempdir(), "aidv_yb_task.json")
```

`worker_chat.js` / `worker_yuanbao.js`：把 `/tmp/aidv_task.json` 换成系统临时目录。

```js
const _os = await import("node:os");
const _path = await import("node:path");
const t0 = JSON.parse(await fs.readFile(_path.join(_os.tmpdir(), "aidv_task.json"), "utf8"));
```

改完自检：

```powershell
python <GEO>\run.py --help
node --check <GEO>\worker_chat.js
node --check <GEO>\worker_yuanbao.js
```
