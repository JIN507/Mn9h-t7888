/* PDF export for the text-detection result: a clean, RTL, print-styled report
   opened in its own window and sent to the browser's print dialog (Save as PDF).
   No extra dependency, no server round-trip. */

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const pct = (v) => `${Math.round((Number(v) || 0) * 100)}%`;

export function buildTextReportHtml(result, text, { appName = 'تحقق' } = {}) {
    const isAI = Boolean(result?.is_ai);
    const when = new Date().toLocaleString('ar-SA', { dateStyle: 'long', timeStyle: 'short' });
    const blocks = Array.isArray(result?.annotations) ? result.annotations : [];
    const flagged = blocks.filter((b) => b.is_ai).length;
    const body = blocks.length
        ? blocks.map((b) => `
            <div class="blk ${b.is_ai ? 'ai' : 'hu'}">
                <div class="tag">${b.is_ai ? 'مولّد آلياً' : 'بشري'} · ${pct(b.confidence)}</div>
                <p>${esc(b.text)}</p>
            </div>`).join('')
        : `<p class="plain">${esc(text)}</p>`;

    return `<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<title>تقرير كشف النص — ${appName}</title>
<style>
  @page { size: A4; margin: 18mm 16mm; }
  * { box-sizing: border-box; }
  body { font-family: "Segoe UI", Tahoma, "Noto Naskh Arabic", Arial, sans-serif; color: #0f172a; margin: 0; padding: 0 4mm; line-height: 1.7; }
  header { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #0f172a; padding-bottom: 10px; margin-bottom: 18px; }
  header .brand { font-weight: 900; font-size: 22px; }
  header .meta { font-size: 12px; color: #64748b; text-align: left; }
  h1 { font-size: 20px; margin: 0 0 6px; }
  .verdict { display: inline-block; padding: 8px 16px; border-radius: 12px; font-weight: 800; font-size: 16px; margin: 6px 0 14px; }
  .verdict.ai { background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; }
  .verdict.hu { background: #f1f5f9; color: #0f172a; border: 1px solid #e2e8f0; }
  .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 18px; }
  .stat { border: 1px solid #e2e8f0; border-radius: 12px; padding: 10px 12px; }
  .stat .l { font-size: 11px; color: #64748b; } .stat .v { font-size: 20px; font-weight: 800; }
  .bar { height: 8px; background: #e2e8f0; border-radius: 6px; overflow: hidden; margin-top: 6px; }
  .bar > i { display: block; height: 100%; background: #0f172a; }
  .bar.hu > i { background: #94a3b8; }
  h2 { font-size: 14px; color: #334155; margin: 18px 0 8px; }
  .blk { border: 1px solid #e2e8f0; border-radius: 10px; padding: 8px 12px; margin-bottom: 8px; page-break-inside: avoid; font-size: 13px; }
  .blk.ai { background: #fff7f7; border-color: #fecaca; }
  .blk .tag { font-size: 11px; font-weight: 700; color: #64748b; margin-bottom: 2px; }
  .blk.ai .tag { color: #b91c1c; }
  .blk p, .plain { margin: 0; white-space: pre-wrap; }
  footer { margin-top: 24px; padding-top: 10px; border-top: 1px solid #e2e8f0; font-size: 11px; color: #64748b; }
</style></head>
<body>
  <header>
    <div class="brand">${appName} — كشف النصوص المولّدة</div>
    <div class="meta">${esc(when)}<br>${blocks.length ? `${blocks.length} فقرة محللة` : ''}</div>
  </header>
  <h1>نتيجة التحليل</h1>
  <div class="verdict ${isAI ? 'ai' : 'hu'}">${esc(result?.verdict || (isAI ? 'نص مُولّد بالذكاء الاصطناعي' : 'نص بشري'))}</div>
  <div class="stats">
    <div class="stat"><div class="l">احتمال التوليد الاصطناعي</div><div class="v">${pct(result?.confidence_ai)}</div><div class="bar"><i style="width:${pct(result?.confidence_ai)}"></i></div></div>
    <div class="stat"><div class="l">احتمال الكتابة البشرية</div><div class="v">${pct(result?.confidence_human)}</div><div class="bar hu"><i style="width:${pct(result?.confidence_human)}"></i></div></div>
    <div class="stat"><div class="l">فقرات مشتبه بتوليدها</div><div class="v">${flagged} / ${blocks.length || 1}</div></div>
  </div>
  <h2>النص مع التحليل التفصيلي</h2>
  ${body}
  <footer>أُنتج هذا التقرير بواسطة ${appName}. نتيجة كشف النصوص تقديرية وتعتمد على نموذج إحصائي؛ يُنصح بدمجها مع أدلة أخرى قبل إصدار حكم.</footer>
  <script>window.addEventListener('load', () => { setTimeout(() => window.print(), 250); });</script>
</body></html>`;
}

export function printTextReport(result, text, opts) {
    const html = buildTextReportHtml(result, text, opts);
    const w = window.open('', '_blank', 'noopener,width=900,height=1000');
    if (!w) return false;
    w.document.open();
    w.document.write(html);
    w.document.close();
    return true;
}
