// 用法：node render.js <input.html> <output.pdf> <页脚文字>
// 用预装的 Playwright + Chromium 把 HTML 打印成 A4 PDF，页脚带页码和合成数据提示。
const path = require('path');
const { chromium } = require('playwright');

(async () => {
  const [html, pdf, footer] = process.argv.slice(2);
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto('file://' + path.resolve(html), { waitUntil: 'networkidle' });
  await page.evaluate(() => document.fonts.ready);
  await page.pdf({
    path: pdf, format: 'A4', printBackground: true, preferCSSPageSize: true,
    displayHeaderFooter: true, headerTemplate: '<span></span>',
    footerTemplate: `<div style="width:100%;font-size:7pt;color:#898781;padding:0 13mm;
      font-family:Inter,'WenQuanYi Zen Hei',sans-serif;display:flex;justify-content:space-between">
      <span>${footer}</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>`,
  });
  await browser.close();
})();
