// 准备 GEO 检测用的 task space：p1=豆包 p2=DeepSeek p3=千问 p4=元宝，并打印 spaceId
const targets = [
  ["p1", "doubao", "https://www.doubao.com/chat/"],
  ["p2", "deepseek", "https://chat.deepseek.com/"],
  ["p3", "qianwen", "https://www.qianwen.com/"],
  ["p4", "yuanbao", "https://yuanbao.tencent.com/chat/naQivTmsDa"],
];

const task = await taskSpace("geo-check-4ai");
const existing = (await task.pages()).map((p) => p.label);
const out = { spaceId: task.spaceId, existing, pages: [] };

for (const [label, name, url] of targets) {
  let page;
  try {
    page = task.page(label);
    if (!existing.includes(label)) page = await task.newPage();
  } catch (e) {
    page = await task.newPage();
  }
  try {
    await page.goto(url, { timeout: 60000 });
    await page.waitForTimeout(2500);
    const info = await page.evaluate(() => ({
      title: document.title,
      url: location.href,
      body: (document.body ? document.body.innerText : "").replace(/\s+/g, " ").slice(0, 120),
    }));
    out.pages.push({ label: page.label, name, ...info });
  } catch (e) {
    out.pages.push({ label: page.label, name, error: String(e).slice(0, 160) });
  }
}
console.log(JSON.stringify(out, null, 1));
