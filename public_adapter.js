/* Public Pages adapter. Filtering operates on the published dataset. */
(function () {
  const originalFetch = window.fetch.bind(window);
  const chinaToday = (date = new Date()) => new Intl.DateTimeFormat('sv-SE', {timeZone: 'Asia/Shanghai'}).format(date);
  function filterRows(rows, params, today = chinaToday()) {
    const kw = (params.get('kw') || '').trim().toLowerCase();
    const op = params.get('operator'), status = params.get('status');
    const days = Number(params.get('days'));
    let from = '';
    if (days > 0) {
      const d = new Date(today + 'T00:00:00Z');
      d.setUTCDate(d.getUTCDate() - days + 1);
      from = d.toISOString().slice(0,10);
    }
    return rows.filter(r =>
      (!kw || [r.title, r.content, r.build_content, r.region, r.winner].some(x => String(x || '').toLowerCase().includes(kw))) &&
      (!op || op === 'all' || r.operator === op) &&
      (!status || status === 'all' || r.status === status) &&
      (!from || ((r.publish_date || '').slice(0,10) >= from && (r.publish_date || '').slice(0,10) <= today))
    );
  }
  window.BidRadarPublic = {filterRows, chinaToday};
  window.BID_RADAR_PUBLIC = true;
  window.fetch = async function(input, options) {
    const url = new URL(String(input), window.location.href);
    if (url.pathname === '/api/bids') {
      const response = await originalFetch('./data/bids.json', {cache: 'no-cache'});
      if (!response.ok) throw new Error('公告数据暂时不可用');
      const data = await response.json();
      const rows = filterRows(data.rows || [], url.searchParams);
      return new Response(JSON.stringify({ok:true, rows, count:rows.length}), {headers:{'Content-Type':'application/json'}});
    }
    if (url.pathname === '/api/stats') return originalFetch('./data/stats.json', {cache:'no-cache'});
    if (url.pathname === '/api/refresh') throw new Error('公网版不提供实时采集，请刷新已发布数据');
    return originalFetch(input, options);
  };
  document.addEventListener('DOMContentLoaded', function() {
    const button = document.getElementById('rf');
    if (button) {
      button.textContent = '刷新数据';
      button.title = '重新读取最近一次发布的数据，不触发官网采集';
      button.onclick = () => load();
    }
    const footer = document.createElement('div');
    footer.style.cssText='text-align:center;padding:20px 10px 34px;color:#8b98a5;font-size:12.5px;line-height:2';
    footer.innerHTML='文档下载：<a href="./docs/usage.pdf" target="_blank" rel="noopener">使用说明</a> · <a href="./docs/requirements.pdf" target="_blank" rel="noopener">需求文档</a><br>公网版展示最近一次发布的数据。云端计划于北京时间每日 09:00 运行，实际更新以采集及发布完成时间为准。';
    document.body.appendChild(footer);
  });
})();
