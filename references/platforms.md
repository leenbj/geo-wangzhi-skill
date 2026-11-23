# 三平台发布：细节、选择器与已知坑

所有发布都走 ego-publish 插件（`egolite_publish`），账号 = 独立 profile = 独立 cookie 罐。
一个「发布单元」= 一篇稿子 → 搜狐号 + 头条号 + CSDN 各发一次，每个平台落一个账号。

## 1. 搜狐号（最稳，首选）

- flow：`sohu__publish-article`（内置，14 步，实测一次跑通）
- 参数：`title`（≤72 字）、`body`（空行分段）、`declaration`（默认「无需声明」）
- 关键步骤：进「发布内容」→ 等 `addarticle` 页 → 填标题 → 填 contenteditable 正文 → 点「发布」→ 回列表页即成功
- 耗时：60–90 秒
- 坑：
  - 「我知道了」弹层有时不存在（optional，不影响）
  - 发布后是**审核中**，只有预览链；公开链接要等过审后到「我的内容」列表读 `h3 a` 的 href
  - 已发布链接形如 `https://www.sohu.com/a/<id>_<accountId>`；`articlepreview` 是预览链，不能当公开链接

## 2. 头条号（坑最多，已修好）

用本 skill 的 `scripts/flows/toutiao__publish-article.json` **覆盖内置版**（内置版会失败）。

修正点：

| 内置版的问题 | 修正 |
|---|---|
| 选「单图」封面但没图 → 点发布无反应 | 改选**「无封面」** |
| 缺「作品声明」→ 点确认发布只关弹层不提交 | 增加一步点**「引用AI」**（稿件为 AI 辅助生成，必须如实勾选）|
| 标题偶尔被草稿重渲染清空 → 提示「还需输入 2 个字」 | 用原生 setter + `input` 事件兜底写入并回读校验 |
| 发布成功后 URL 常不跳转 → 被误判为失败 → 重复提交 | 最后一步 URL 等待设为 **optional**，以**作品列表出现标题**为判据 |

- 参数：`title`（**≤30 字**，硬限制）、`body`
- 耗时：40–120 秒
- **v7 关键改动（防重复）**：提交步从 `click` 动作改成 **eval 单次 DOM 点击 + `window.__ksClicked` 标记**。
  旧版用 `click` 时，确认弹层关闭后引擎会重试一次点击，导致同一篇发出两条（实测 `t-2`、`t-3` 各一次）。
- 判定发布成功：`https://mp.toutiao.com/profile_v4/graphic/articles` 列表里出现该标题
- 重复发布是真实风险：实测在 `t-2` 把同一篇发了 2 条。**点「确认发布」前先确认弹层真的出现**；点完先查列表，别急着重试。

## 3. CSDN（当前暂缓）

- flow：`scripts/flows/csdn__publish-article.json`
- 参数：`title`（≤100 字）、`body`、`tag`
- 编辑器是 CKEditor4，在 iframe `.cke_wysiwyg_frame` 里
- 实测必须遵守：
  1. **按段落逐段输入**（每段 `type` 一次 + 间隔 ~300 ms）。整段 900+ 字一次性 `type` 会把编辑器主线程卡死（`Runtime.evaluate did not answer within 15000ms`，正文 0 字）
  2. **必须加文章标签**（点「添加文章标签」→ 输入 `input[placeholder*='自定义标签']` → Enter），否则点「发布博客」不提交
  3. 正文校验用 iframe 内 `contentDocument.body.innerText` 长度，别用页面的「共 N 字」计数器（口径不同）
- 已知未解决问题：部分账号点「发布博客」既不跳转也不报错（b-2 复现；同流程在 b-1 成功）。当前策略：**CSDN 暂缓发布**，优先保证搜狐 + 头条产能。
- 成功页：`https://mp.csdn.net/mp_blog/creation/success/<文章ID>`

## 4. 网易号（只在需要时用）

- flow：`scripts/flows/netease__publish-article.json`（新版页面：标题 `textarea.netease-textarea`、正文 `.public-DraftEditor-content`、封面点「自动」）
- 独立脚本：`scripts/publish_netease.py`（Playwright + 账号 profile，带备份/回滚）
- **致命约束**：网易号的登录 cookie 是会话级，浏览器一关就掉。只能「窗口常开 + 同会话发布」；巡检必须跳过它（`check_logins.py` 默认已跳过）
- 正文 ≥250 字才分发；标题 5–64 字；新版页面不需要分类/标签

## 5. 通用规则

- 同一账号两次发布间隔 **45–150 分钟**（插件强制），不要连发
- 一个账号一天 5 篇 = 3 案例 + 2 科普
- 发布前必须 `dryRun:true` 彩排一次（填表 + 截图，不提交），确认标题/正文/封面都对
- 失败先读 run 目录：`~/.dsh/ego-publish/runs/<时间戳>-<flow>-<账号>/`（每步截图 + 步骤状态）
- 登录失效：`egolite_account {op:"login", code:"<代号>"}` 请用户扫码，别反复重试

## 6. 账号代号约定

| 前缀 | 平台 |
|---|---|
| `a-*` | 搜狐号 |
| `t-*` | 头条号 |
| `b-*` | CSDN |
| `c-*` | 网易号 |

一组 = 同编号的 `a-N / t-N / b-N`；8 组 ≈ 每天 40 篇（受写稿速度限制）。
