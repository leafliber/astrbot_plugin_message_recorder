const bridge = window.AstrBotPluginPage;

const PLUGIN_NAME = 'astrbot_plugin_message_recorder';

let bridgeReady = false;

async function init() {
  await bridge.ready();
  bridgeReady = true;
  initRouter();
  initDashboard();
  initSearch();
  initExport();
  initImport();
  initModal();
  initNavToggle();
  navigateToDefault();
}

function initRouter() {
  window.addEventListener('hashchange', handleHashChange);
}

function handleHashChange() {
  const hash = window.location.hash.slice(1) || 'dashboard';
  switchView(hash);
}

function navigateToDefault() {
  const hash = window.location.hash.slice(1) || 'dashboard';
  switchView(hash);
}

function switchView(viewName) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-link').forEach(a => a.classList.remove('active'));

  const view = document.getElementById(`view-${viewName}`);
  if (view) {
    view.classList.add('active');
  } else {
    document.getElementById('view-dashboard').classList.add('active');
    viewName = 'dashboard';
  }

  const navLink = document.querySelector(`.nav-link[data-view="${viewName}"]`);
  if (navLink) navLink.classList.add('active');

  if (viewName === 'dashboard') loadDashboardData();
  if (viewName === 'search') loadSearchData();
  if (viewName === 'export') loadExportData();
}

function initNavToggle() {
  document.getElementById('navToggle')?.addEventListener('click', () => {
    document.getElementById('navLinks')?.classList.toggle('show');
  });
}

function showLoading() {
  const el = document.getElementById('loadingOverlay');
  if (el) el.style.display = 'flex';
}

function hideLoading() {
  const el = document.getElementById('loadingOverlay');
  if (el) el.style.display = 'none';
}

function formatTime(timestamp) {
  const date = new Date(timestamp);
  return date.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  });
}

function formatShortTime(timestamp) {
  const date = new Date(timestamp);
  return date.toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'
  });
}

function formatNumber(num) {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
  return num.toString();
}

function formatFileSize(size) {
  if (size < 1024) return size + ' B';
  if (size < 1024 * 1024) return (size / 1024).toFixed(1) + ' KB';
  if (size < 1024 * 1024 * 1024) return (size / (1024 * 1024)).toFixed(1) + ' MB';
  return (size / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
}

function getPlatformIcon(platform) {
  const icons = {
    'telegram': 'TG', 'discord': 'DC',
    'qq_official': 'QQ', 'qq_private': 'QQ', 'wechat': 'WX'
  };
  return icons[platform] || platform;
}

function escapeHtml(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function truncate(str, maxLen = 100) {
  if (!str) return '';
  if (str.length <= maxLen) return str;
  return str.substring(0, maxLen) + '...';
}

function parseTimeRangeClient(timeRange) {
  const now = new Date();
  let start, end;
  switch (timeRange) {
    case 'today':
      start = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0);
      end = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59);
      break;
    case 'yesterday': {
      const y = new Date(now);
      y.setDate(now.getDate() - 1);
      start = new Date(y.getFullYear(), y.getMonth(), y.getDate(), 0, 0, 0);
      end = new Date(y.getFullYear(), y.getMonth(), y.getDate(), 23, 59, 59);
      break;
    }
    case 'last7d':
      start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
      end = now;
      break;
    case 'last30d':
      start = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
      end = now;
      break;
    case 'week': {
      const dow = now.getDay() || 7;
      const ws = new Date(now);
      ws.setDate(now.getDate() - dow + 1);
      start = new Date(ws.getFullYear(), ws.getMonth(), ws.getDate(), 0, 0, 0);
      end = now;
      break;
    }
    case 'month':
      start = new Date(now.getFullYear(), now.getMonth(), 1, 0, 0, 0);
      end = now;
      break;
    default:
      start = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
      end = now;
  }
  return { start: start.getTime(), end: end.getTime() };
}

const timeRangeLabels = {
  'today': '今日', 'yesterday': '昨日', 'last7d': '最近7天',
  'last30d': '最近30天', 'week': '本周', 'month': '本月'
};

function formatTimestampStr(ts) {
  const date = new Date(ts);
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  const h = String(date.getHours()).padStart(2, '0');
  const min = String(date.getMinutes()).padStart(2, '0');
  const s = String(date.getSeconds()).padStart(2, '0');
  return `${y}-${m}-${d} ${h}:${min}:${s}`;
}

// ========== Dashboard ==========

let timelineChart = null;
let platformChart = null;
let senderChart = null;
let groupChart = null;
let currentTimeRange = 'last30d';

function initDashboard() {
  document.querySelectorAll('.time-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      document.querySelectorAll('.time-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentTimeRange = btn.dataset.range;
      updateTimeRangeDisplay(currentTimeRange);
      await loadRankingData();
    });
  });
}

async function loadDashboardData() {
  showLoading();
  try {
    const statsResult = await bridge.apiGet('stats');
    if (statsResult.success) {
      updateStatsCards(statsResult.data);
      updatePlatformChart(statsResult.data.platform_stats);
    }
    const timelineResult = await bridge.apiGet('stats/timeline', { interval: 'day' });
    if (timelineResult.success) {
      updateTimelineChart(timelineResult.data.points);
    }
    updateTimeRangeDisplay(currentTimeRange);
    await loadRankingData();
  } finally {
    hideLoading();
  }
}

async function loadRankingData() {
  const senderResult = await bridge.apiGet('stats/senders', { limit: 10, time: currentTimeRange });
  if (senderResult.success) updateSenderChart(senderResult.data.senders);

  const groupResult = await bridge.apiGet('stats/groups', { limit: 10, time: currentTimeRange });
  if (groupResult.success) updateGroupChart(groupResult.data.groups);
}

function updateStatsCards(stats) {
  const el = (id) => document.getElementById(id);
  if (el('totalCount')) el('totalCount').textContent = formatNumber(stats.total_count);
  if (el('groupCount')) el('groupCount').textContent = formatNumber(stats.group_message_count);
  if (el('privateCount')) el('privateCount').textContent = formatNumber(stats.private_message_count);
  if (el('platformCount')) el('platformCount').textContent = stats.platform_count;
}

function updateTimeRangeDisplay(timeRange) {
  const el = document.getElementById('timeRangeInfo');
  if (!el) return;
  const { start, end } = parseTimeRangeClient(timeRange);
  const label = timeRangeLabels[timeRange] || timeRange;
  el.innerHTML = `<span class="time-range-label">${label}</span> <span class="time-range-separator">|</span> <span class="time-range-value">${formatTimestampStr(start)} ~ ${formatTimestampStr(end)}</span>`;
}

function initCharts() {
  const make = (id) => {
    const el = document.getElementById(id);
    return el ? echarts.init(el) : null;
  };
  if (!timelineChart) timelineChart = make('timelineChart');
  if (!platformChart) platformChart = make('platformChart');
  if (!senderChart) senderChart = make('senderChart');
  if (!groupChart) groupChart = make('groupChart');

  window.addEventListener('resize', () => {
    timelineChart?.resize();
    platformChart?.resize();
    senderChart?.resize();
    groupChart?.resize();
  });
}

function updateTimelineChart(points) {
  if (typeof echarts === 'undefined') return;
  initCharts();
  if (!timelineChart || !points?.length) return;

  timelineChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: { data: ['总消息', '群聊', '私聊'] },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'category', data: points.map(p => p.date), axisLabel: { rotate: 45 } },
    yAxis: { type: 'value' },
    series: [
      { name: '总消息', type: 'line', data: points.map(p => p.count), smooth: true, areaStyle: { opacity: 0.3 } },
      { name: '群聊', type: 'line', data: points.map(p => p.group_count), smooth: true },
      { name: '私聊', type: 'line', data: points.map(p => p.private_count), smooth: true }
    ]
  });
}

function updatePlatformChart(platformStats) {
  if (typeof echarts === 'undefined') return;
  initCharts();
  if (!platformChart || !platformStats) return;

  const data = Object.entries(platformStats).map(([name, value]) => ({
    name: getPlatformIcon(name), value
  }));

  platformChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { orient: 'vertical', right: '5%', top: 'center' },
    series: [{
      type: 'pie', radius: ['40%', '70%'], center: ['40%', '50%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 10, borderColor: '#fff', borderWidth: 2 },
      label: { show: false, position: 'center' },
      emphasis: { label: { show: true, fontSize: 20, fontWeight: 'bold' } },
      labelLine: { show: false },
      data
    }]
  });
}

function updateSenderChart(senders) {
  if (typeof echarts === 'undefined') return;
  initCharts();
  if (!senderChart || !senders?.length) return;

  senderChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '3%', right: '10%', bottom: '3%', containLabel: true },
    xAxis: { type: 'value' },
    yAxis: { type: 'category', data: senders.map(s => truncate(s.sender_name || s.sender_id, 15)).reverse(), axisLabel: { width: 100, overflow: 'truncate' } },
    series: [{ type: 'bar', data: senders.map(s => s.count).reverse(), itemStyle: { color: '#3498db', borderRadius: [0, 4, 4, 0] } }]
  });
}

function updateGroupChart(groups) {
  if (typeof echarts === 'undefined') return;
  initCharts();
  if (!groupChart || !groups?.length) return;

  groupChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '3%', right: '10%', bottom: '3%', containLabel: true },
    xAxis: { type: 'value' },
    yAxis: { type: 'category', data: groups.map(g => truncate(g.group_id, 20)).reverse(), axisLabel: { width: 100, overflow: 'truncate' } },
    series: [{ type: 'bar', data: groups.map(g => g.count).reverse(), itemStyle: { color: '#27ae60', borderRadius: [0, 4, 4, 0] } }]
  });
}

// ========== Search ==========

let searchFilters = { limit: 50, offset: 0, order: 'desc' };
let totalMessages = 0;
let advancedVisible = false;

function initSearch() {
  const keywordInput = document.getElementById('keywordInput');
  if (keywordInput) {
    let timer;
    keywordInput.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        searchFilters.keyword = keywordInput.value.trim();
        searchFilters.offset = 0;
        loadMessages();
      }, 300);
    });
  }

  const bindSelect = (id, key) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('change', () => {
      searchFilters[key] = el.value;
      searchFilters.offset = 0;
      if (id === 'platformFilter') {
        loadGroups(el.value);
        loadSenders(el.value);
      }
      loadMessages();
    });
  };

  bindSelect('platformFilter', 'platform');
  bindSelect('typeFilter', 'message_type');
  bindSelect('orderFilter', 'order');

  const limitEl = document.getElementById('limitFilter');
  if (limitEl) limitEl.addEventListener('change', () => {
    searchFilters.limit = parseInt(limitEl.value);
    searchFilters.offset = 0;
    loadMessages();
  });

  document.getElementById('toggleAdvancedBtn')?.addEventListener('click', () => {
    advancedVisible = !advancedVisible;
    document.getElementById('advancedFilters').style.display = advancedVisible ? 'flex' : 'none';
    document.getElementById('toggleAdvancedBtn').textContent = advancedVisible ? '收起筛选' : '展开更多筛选';
  });

  document.getElementById('refreshBtn')?.addEventListener('click', () => loadMessages());
  document.getElementById('exportResultsBtn')?.addEventListener('click', () => {
    window.location.hash = '#export';
    exportFilters = { ...searchFilters };
    displayExportFilters();
  });
}

async function loadSearchData() {
  await loadPlatforms();
  await loadMessages();
}

async function loadPlatforms() {
  const result = await bridge.apiGet('platforms');
  if (!result.success) return;

  const selects = ['platformFilter', 'exportPlatform'];
  selects.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    const currentVal = el.value;
    el.innerHTML = '<option value="">全部平台</option>';
    result.data.platforms.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p;
      opt.textContent = getPlatformIcon(p);
      el.appendChild(opt);
    });
    el.value = currentVal;
  });
}

async function loadGroups(platform) {
  const result = await bridge.apiGet('groups', { platform, limit: 100 });
  if (!result.success) return;
  const el = document.getElementById('groupFilter');
  if (!el) return;
  el.innerHTML = '<option value="">全部群组</option>';
  result.data.groups.forEach(g => {
    const opt = document.createElement('option');
    opt.value = g.id;
    opt.textContent = truncate(g.id, 30);
    el.appendChild(opt);
  });
}

async function loadSenders(platform) {
  const result = await bridge.apiGet('senders', { platform, limit: 100 });
  if (!result.success) return;
  const el = document.getElementById('senderFilter');
  if (!el) return;
  el.innerHTML = '<option value="">全部发送者</option>';
  result.data.senders.forEach(s => {
    const opt = document.createElement('option');
    opt.value = s.id;
    opt.textContent = truncate(s.name, 30);
    el.appendChild(opt);
  });
}

async function loadMessages() {
  showLoading();
  try {
    const groupEl = document.getElementById('groupFilter');
    const senderEl = document.getElementById('senderFilter');
    const startEl = document.getElementById('startTimeInput');
    const endEl = document.getElementById('endTimeInput');

    if (groupEl?.value) searchFilters.group_id = groupEl.value;
    else delete searchFilters.group_id;
    if (senderEl?.value) searchFilters.sender_id = senderEl.value;
    else delete searchFilters.sender_id;
    if (startEl?.value) searchFilters.start_time = new Date(startEl.value).getTime();
    else delete searchFilters.start_time;
    if (endEl?.value) searchFilters.end_time = new Date(endEl.value).getTime();
    else delete searchFilters.end_time;

    const result = await bridge.apiGet('messages', searchFilters);
    if (!result.success) {
      showMessageError(result.error);
      return;
    }
    totalMessages = result.data.pagination.total;
    renderMessages(result.data.messages);
    renderPagination(result.data.pagination);
  } finally {
    hideLoading();
  }
}

function renderMessages(messages) {
  const container = document.getElementById('messageList');
  if (!container) return;
  if (!messages.length) {
    container.innerHTML = '<p class="text-center text-muted">暂无消息记录</p>';
    return;
  }
  container.innerHTML = messages.map(msg => `
    <div class="message-card" data-id="${msg.id}">
      <div class="message-header">
        <span class="message-time">${formatShortTime(msg.timestamp)}</span>
        <span class="message-platform">${getPlatformIcon(msg.platform)}</span>
        <span class="message-type">${msg.message_type === 'group' ? '群聊' : '私聊'}</span>
        <span class="message-sender">${escapeHtml(msg.sender_name || msg.sender_id)}</span>
      </div>
      <div class="message-content">${escapeHtml(truncate(msg.message_str, 200))}</div>
      <div class="message-actions">
        <a data-action="detail" data-id="${msg.id}">查看详情</a>
        <a data-action="context" data-id="${msg.id}">查看上下文</a>
      </div>
    </div>
  `).join('');

  container.querySelectorAll('[data-action="detail"]').forEach(a => {
    a.addEventListener('click', (e) => { e.stopPropagation(); showMessageDetail(parseInt(a.dataset.id)); });
  });
  container.querySelectorAll('[data-action="context"]').forEach(a => {
    a.addEventListener('click', (e) => { e.stopPropagation(); showMessageContext(parseInt(a.dataset.id)); });
  });
  container.querySelectorAll('.message-card').forEach(card => {
    card.addEventListener('click', () => showMessageDetail(parseInt(card.dataset.id)));
  });
}

function showMessageError(error) {
  const container = document.getElementById('messageList');
  if (container) container.innerHTML = `<p class="text-center text-muted">加载失败: ${escapeHtml(error)}</p>`;
}

function renderPagination(pagination) {
  const container = document.getElementById('pagination');
  if (!container) return;
  const { total, limit, offset } = pagination;
  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(total / limit);

  if (totalPages <= 1) {
    container.innerHTML = `<span class="pagination-info">共 ${total} 条记录</span>`;
    return;
  }

  container.innerHTML = `
    <button class="pagination-btn ${currentPage <= 1 ? 'disabled' : ''}" id="prevPage" ${currentPage <= 1 ? 'disabled' : ''}>上一页</button>
    <span class="pagination-info">第 ${currentPage}/${totalPages} 页，共 ${total} 条</span>
    <button class="pagination-btn ${currentPage >= totalPages ? 'disabled' : ''}" id="nextPage" ${currentPage >= totalPages ? 'disabled' : ''}>下一页</button>
  `;

  document.getElementById('prevPage')?.addEventListener('click', () => {
    if (currentPage > 1) { searchFilters.offset = (currentPage - 2) * searchFilters.limit; loadMessages(); }
  });
  document.getElementById('nextPage')?.addEventListener('click', () => {
    if (currentPage < totalPages) { searchFilters.offset = currentPage * searchFilters.limit; loadMessages(); }
  });
}

// ========== Modal ==========

function initModal() {
  const modal = document.getElementById('messageModal');
  document.getElementById('modalClose')?.addEventListener('click', hideModal);
  modal?.addEventListener('click', (e) => { if (e.target === modal) hideModal(); });
}

function showModal(content) {
  const body = document.getElementById('modalBody');
  if (body) body.innerHTML = content;
  document.getElementById('messageModal')?.classList.add('show');
}

function hideModal() {
  document.getElementById('messageModal')?.classList.remove('show');
}

async function showMessageDetail(messageId) {
  showLoading();
  const result = await bridge.apiGet(`messages/${messageId}`);
  hideLoading();
  if (!result.success) { showModal(`<p class="text-muted">加载失败: ${result.error}</p>`); return; }

  const msg = result.data;
  showModal(`
    <div class="detail-section">
      <div class="detail-row"><span class="detail-label">时间:</span><span class="detail-value">${formatTime(msg.timestamp)}</span></div>
      <div class="detail-row"><span class="detail-label">平台:</span><span class="detail-value">${getPlatformIcon(msg.platform)}</span></div>
      <div class="detail-row"><span class="detail-label">发送者:</span><span class="detail-value">${escapeHtml(msg.sender_name || msg.sender_id)}</span></div>
      <div class="detail-row"><span class="detail-label">消息类型:</span><span class="detail-value">${msg.message_type === 'group' ? '群聊' : '私聊'}</span></div>
      ${msg.group_id ? `<div class="detail-row"><span class="detail-label">群组:</span><span class="detail-value">${escapeHtml(msg.group_id)}</span></div>` : ''}
      <div class="detail-row"><span class="detail-label">内容:</span><span class="detail-value">${escapeHtml(msg.message_str) || '[非文本消息]'}</span></div>
    </div>
    ${msg.message_chain?.length ? `
    <div class="detail-section mt-2">
      <h4>消息链</h4>
      <pre style="background:#f5f6fa;padding:0.5rem;border-radius:4px;overflow-x:auto;font-size:0.85rem;">${escapeHtml(JSON.stringify(msg.message_chain, null, 2))}</pre>
    </div>` : ''}
    <div class="message-actions mt-2">
      <a id="contextLink" data-id="${msg.id}" style="color:var(--primary-color);cursor:pointer;">查看上下文</a>
    </div>
  `);

  document.getElementById('contextLink')?.addEventListener('click', () => {
    showMessageContext(msg.id);
  });
}

async function showMessageContext(messageId) {
  showLoading();
  const result = await bridge.apiGet(`messages/${messageId}/context`, { before: 5, after: 5 });
  hideLoading();
  if (!result.success) { showModal(`<p class="text-muted">加载失败: ${result.error}</p>`); return; }

  const data = result.data;
  let content = '<h4>上下文消息</h4>';
  if (data.before?.length) {
    content += '<div class="mb-1"><strong>前文:</strong></div>';
    data.before.forEach(msg => {
      content += `<div class="context-message"><span class="text-muted">${formatShortTime(msg.timestamp)}</span> <strong>${escapeHtml(msg.sender_name || msg.sender_id)}</strong>: ${escapeHtml(truncate(msg.message_str))}</div>`;
    });
  }
  content += `<div class="context-message highlight"><span class="text-muted">${formatShortTime(data.target.timestamp)}</span> <strong>${escapeHtml(data.target.sender_name || data.target.sender_id)}</strong>: ${escapeHtml(data.target.message_str) || '[非文本消息]'}</div>`;
  if (data.after?.length) {
    content += '<div class="mt-2 mb-1"><strong>后文:</strong></div>';
    data.after.forEach(msg => {
      content += `<div class="context-message"><span class="text-muted">${formatShortTime(msg.timestamp)}</span> <strong>${escapeHtml(msg.sender_name || msg.sender_id)}</strong>: ${escapeHtml(truncate(msg.message_str))}</div>`;
    });
  }
  showModal(content);
}

// ========== Export ==========

let selectedFormat = 'json';
let exportFilters = {};

function initExport() {
  document.querySelectorAll('.format-option').forEach(opt => {
    opt.addEventListener('click', () => {
      document.querySelectorAll('.format-option').forEach(o => o.classList.remove('selected'));
      opt.classList.add('selected');
      selectedFormat = opt.dataset.format;
    });
  });

  const mediaCheckbox = document.getElementById('includeMedia');
  const mediaNote = document.getElementById('mediaNote');
  if (mediaCheckbox && mediaNote) {
    mediaCheckbox.addEventListener('change', () => {
      mediaNote.style.display = mediaCheckbox.checked ? 'block' : 'none';
      if (mediaCheckbox.checked && selectedFormat !== 'json') {
        selectedFormat = 'json';
        document.querySelectorAll('.format-option').forEach(o => o.classList.remove('selected'));
        document.querySelector('.format-option[data-format="json"]')?.classList.add('selected');
      }
    });
  }

  const bindExportFilter = (id, key, isTime) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('change', () => {
      if (el.value) {
        exportFilters[key] = isTime ? new Date(el.value).getTime() : el.value;
        if (isTime) delete exportFilters.time;
      } else {
        delete exportFilters[key];
      }
    });
  };

  bindExportFilter('exportTime', 'time', false);
  bindExportFilter('exportPlatform', 'platform', false);
  bindExportFilter('exportType', 'message_type', false);
  bindExportFilter('exportStartTime', 'start_time', true);
  bindExportFilter('exportEndTime', 'end_time', true);

  const keywordEl = document.getElementById('exportKeyword');
  if (keywordEl) keywordEl.addEventListener('input', () => {
    if (keywordEl.value.trim()) exportFilters.keyword = keywordEl.value.trim();
    else delete exportFilters.keyword;
  });

  document.getElementById('startExport')?.addEventListener('click', startExport);
}

async function loadExportData() {
  await loadPlatforms();
  displayExportFilters();
}

function displayExportFilters() {
  const container = document.getElementById('currentFilters');
  if (!container) return;
  const entries = Object.entries(exportFilters).filter(([, v]) => v);
  if (!entries.length) { container.innerHTML = ''; return; }
  container.innerHTML = '<p>当前筛选条件:</p><ul>' +
    entries.map(([k, v]) => `<li><strong>${k}</strong>: ${v}</li>`).join('') +
    '</ul>';
}

async function startExport() {
  const includeMedia = document.getElementById('includeMedia')?.checked ?? false;
  if (includeMedia && selectedFormat !== 'json') {
    alert('包含多媒体文件选项仅支持 JSON 格式导出');
    return;
  }

  const options = {
    include_chain: document.getElementById('includeChain')?.checked ?? true,
    include_raw: document.getElementById('includeRaw')?.checked ?? false,
    include_media: includeMedia
  };

  showLoading();
  const result = await bridge.apiPost('export', { format: selectedFormat, filters: exportFilters, options });
  hideLoading();

  if (!result.success) { alert('创建导出任务失败: ' + result.error); return; }
  showExportProgress(result.data);
}

function showExportProgress(task) {
  const container = document.getElementById('exportProgress');
  if (!container) return;
  container.style.display = 'block';
  container.innerHTML = `
    <div class="card">
      <h3>导出任务 #${task.task_id}</h3>
      <p>预计数量: ${task.estimated_count} 条</p>
      <p>预计大小: ${task.estimated_size}</p>
      <div class="task-progress"><div class="progress-bar" id="exportProgressBar" style="width: 0%"></div></div>
      <p id="exportTaskStatus">准备中...</p>
      <button class="btn btn-success hidden" id="downloadBtn">下载文件</button>
    </div>
  `;
  pollExportStatus(task.task_id);
}

async function pollExportStatus(taskId) {
  const statusEl = document.getElementById('exportTaskStatus');
  const progressEl = document.getElementById('exportProgressBar');
  const downloadBtn = document.getElementById('downloadBtn');

  let status = 'pending';
  while (status !== 'completed' && status !== 'failed') {
    await new Promise(r => setTimeout(r, 1000));
    const result = await bridge.apiGet(`export/status/${taskId}`);
    if (!result.success) break;
    status = result.data.status;

    const statusText = { pending: '准备中...', processing: '处理中...', completed: '已完成!', failed: '失败' };
    if (statusEl) statusEl.textContent = statusText[status] || status;
    if (progressEl) progressEl.style.width = status === 'completed' ? '100%' : status === 'processing' ? '50%' : '0%';

    if (downloadBtn && status === 'completed') {
      downloadBtn.classList.remove('hidden');
      downloadBtn.addEventListener('click', () => {
        bridge.download(`export/download/${taskId}`, {}, `messages_export.zip`);
      });
    }
  }
}

// ========== Import ==========

let selectedImportMode = 'merge';
let selectedImportFile = null;
const CHUNK_THRESHOLD = 50 * 1024 * 1024;
const CHUNK_SIZE_JS = 5 * 1024 * 1024;

function initImport() {
  const uploadArea = document.getElementById('uploadArea');
  const fileInput = document.getElementById('importFile');

  if (uploadArea && fileInput) {
    uploadArea.addEventListener('click', () => fileInput.click());
    uploadArea.addEventListener('dragover', (e) => { e.preventDefault(); uploadArea.classList.add('dragover'); });
    uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('dragover'));
    uploadArea.addEventListener('drop', (e) => {
      e.preventDefault();
      uploadArea.classList.remove('dragover');
      if (e.dataTransfer.files.length > 0) handleFileSelect(e.dataTransfer.files[0]);
    });
    fileInput.addEventListener('change', () => {
      if (fileInput.files.length > 0) handleFileSelect(fileInput.files[0]);
    });
  }

  document.querySelectorAll('input[name="importMode"]').forEach(radio => {
    radio.addEventListener('change', () => { selectedImportMode = radio.value; });
  });

  document.getElementById('startImport')?.addEventListener('click', startImport);
}

function handleFileSelect(file) {
  const fileInfo = document.getElementById('fileInfo');
  if (!fileInfo) return;

  const validFormats = ['.json', '.csv', '.mrpkg'];
  const fileExt = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
  if (!validFormats.includes(fileExt)) {
    alert('请选择 JSON、CSV 或 MRPKG 格式的文件');
    return;
  }

  fileInfo.style.display = 'block';
  const formatLabel = fileExt === '.mrpkg' ? 'MRPKG（含媒体文件包）' : fileExt.toUpperCase().slice(1);
  fileInfo.innerHTML = `
    <p>已选择文件: <strong>${file.name}</strong></p>
    <p>文件大小: ${formatFileSize(file.size)}</p>
    <p>格式: ${formatLabel}</p>
  `;
  selectedImportFile = file;
}

async function startImport() {
  if (!selectedImportFile) { alert('请先选择要导入的文件'); return; }

  if (selectedImportFile.size > CHUNK_THRESHOLD) {
    await startChunkedImport(selectedImportFile);
  } else {
    await startSimpleImport(selectedImportFile);
  }
}

async function startSimpleImport(file) {
  showLoading();
  try {
    const result = await bridge.upload('import/upload', file);
    hideLoading();
    if (!result.success) { alert('导入失败: ' + result.error); return; }
    showImportProgress(result.data);
  } catch (e) {
    hideLoading();
    alert('导入失败: ' + e.message);
  }
}

async function startChunkedImport(file) {
  const initResult = await bridge.apiPost('import/init', {
    filename: file.name,
    file_size: file.size,
    mode: selectedImportMode
  });
  if (!initResult.success) { alert('初始化分片上传失败: ' + initResult.error); return; }

  const { session_id, total_chunks } = initResult.data;
  showChunkUploadProgress(file.name, total_chunks);

  let uploadedCount = 0;
  for (let i = 0; i < total_chunks; i++) {
    const start = i * CHUNK_SIZE_JS;
    const end = Math.min(start + CHUNK_SIZE_JS, file.size);
    const chunkBlob = file.slice(start, end);

    try {
      const chunkResult = await bridge.upload(`import/chunk/${session_id}/${i}`, chunkBlob);
      if (!chunkResult.success) {
        alert(`上传分片 ${i + 1}/${total_chunks} 失败: ${chunkResult.error}`);
        return;
      }
      uploadedCount++;
      updateChunkUploadProgress(uploadedCount, total_chunks);
    } catch (e) {
      alert(`上传分片 ${i + 1}/${total_chunks} 失败: ${e.message}`);
      return;
    }
  }

  const completeResult = await bridge.apiPost('import/complete', { session_id });
  if (!completeResult.success) { alert('完成上传失败: ' + completeResult.error); return; }
  showImportProgress(completeResult.data);
}

function showChunkUploadProgress(filename, totalChunks) {
  const container = document.getElementById('importProgress');
  if (!container) return;
  container.style.display = 'block';
  container.innerHTML = `
    <div class="card">
      <h3>上传文件: ${escapeHtml(filename)}</h3>
      <p>使用分片上传，共 ${totalChunks} 个分片</p>
      <div class="task-progress" style="margin:1rem 0;"><div class="progress-bar" id="chunkProgressBar" style="width:0%;transition:width 0.3s ease;"></div></div>
      <p id="chunkProgressText">已上传: 0 / ${totalChunks} 分片 (0%)</p>
    </div>
  `;
}

function updateChunkUploadProgress(uploaded, total) {
  const percent = Math.round((uploaded / total) * 100);
  const bar = document.getElementById('chunkProgressBar');
  const text = document.getElementById('chunkProgressText');
  if (bar) bar.style.width = percent + '%';
  if (text) text.textContent = `已上传: ${uploaded} / ${total} 分片 (${percent}%)`;
}

function showImportProgress(task) {
  const container = document.getElementById('importProgress');
  if (!container) return;
  container.style.display = 'block';
  container.innerHTML = `
    <div class="card">
      <h3>导入任务 #${task.task_id}</h3>
      <p>文件: ${escapeHtml(task.filename)}</p>
      <p>模式: ${task.mode === 'merge' ? '合并' : task.mode === 'skip_duplicates' ? '跳过重复' : '替换'}</p>
      <div class="task-stats">
        <div class="task-stat"><div class="task-stat-value" id="importProcessed">0</div><div class="task-stat-label">已处理</div></div>
        <div class="task-stat"><div class="task-stat-value" id="importImported">0</div><div class="task-stat-label">已导入</div></div>
        <div class="task-stat"><div class="task-stat-value" id="importSkipped">0</div><div class="task-stat-label">已跳过</div></div>
        <div class="task-stat"><div class="task-stat-value" id="importErrors">0</div><div class="task-stat-label">错误</div></div>
        <div class="task-stat"><div class="task-stat-value" id="importMediaRestored">0</div><div class="task-stat-label">媒体文件</div></div>
      </div>
      <div class="task-progress"><div class="progress-bar" id="importProgressBar" style="width:0%"></div></div>
      <p id="importTaskStatus">准备中...</p>
    </div>
  `;
  pollImportStatus(task.task_id);
}

async function pollImportStatus(taskId) {
  const statusEl = document.getElementById('importTaskStatus');
  const progressEl = document.getElementById('importProgressBar');

  let status = 'pending';
  while (status !== 'completed' && status !== 'failed') {
    await new Promise(r => setTimeout(r, 500));
    const result = await bridge.apiGet(`import/status/${taskId}`);
    if (!result.success) break;
    const task = result.data;
    status = task.status;

    const statusText = { pending: '准备中...', processing: '处理中...', completed: '已完成!', failed: '失败: ' + (task.error || '') };
    if (statusEl) statusEl.textContent = statusText[status] || status;

    const el = (id) => document.getElementById(id);
    if (el('importProcessed')) el('importProcessed').textContent = task.processed || 0;
    if (el('importImported')) el('importImported').textContent = task.imported || 0;
    if (el('importSkipped')) el('importSkipped').textContent = task.skipped || 0;
    if (el('importErrors')) el('importErrors').textContent = task.errors || 0;
    if (el('importMediaRestored')) el('importMediaRestored').textContent = task.media_restored || 0;

    if (progressEl && task.total_records > 0) {
      progressEl.style.width = Math.round((task.processed / task.total_records) * 100) + '%';
    }
  }
}

// ========== Init ==========

init();
