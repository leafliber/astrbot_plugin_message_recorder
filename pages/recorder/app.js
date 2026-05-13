const bridge = window.AstrBotPluginPage;

const PLUGIN_NAME = 'astrbot_plugin_message_recorder';

let bridgeReady = false;
let pluginContext = null;

const DEBUG = new URLSearchParams(window.location.search).has('debug');

function log(...args) {
  if (DEBUG) console.log('[MessageRecorder]', ...args);
}

function logError(...args) {
  console.error('[MessageRecorder]', ...args);
}

async function apiGet(endpoint, params) {
  if (!bridge || !bridgeReady) {
    logError('Bridge not ready for apiGet:', endpoint);
    return { success: false, error: 'Bridge SDK 未就绪' };
  }
  try {
    log('apiGet:', endpoint, params);
    const result = await bridge.apiGet(endpoint, params);
    log('apiGet response:', endpoint, result);
    return result;
  } catch (e) {
    logError('apiGet failed:', endpoint, e);
    return { success: false, error: e.message || String(e) };
  }
}

async function apiPost(endpoint, body) {
  if (!bridge || !bridgeReady) {
    logError('Bridge not ready for apiPost:', endpoint);
    return { success: false, error: 'Bridge SDK 未就绪' };
  }
  try {
    log('apiPost:', endpoint, body);
    const result = await bridge.apiPost(endpoint, body);
    log('apiPost response:', endpoint, result);
    return result;
  } catch (e) {
    logError('apiPost failed:', endpoint, e);
    return { success: false, error: e.message || String(e) };
  }
}

function showInitError(message) {
  const main = document.querySelector('.main-content');
  if (main) {
    const existing = document.getElementById('initError');
    if (existing) existing.remove();
    const div = document.createElement('div');
    div.id = 'initError';
    div.style.cssText = 'padding:2rem;text-align:center;color:#e74c3c;';
    div.innerHTML = `<h3>⚠️ 初始化失败</h3><p>${message}</p><p style="color:#999;font-size:0.85rem;">请确保 AstrBot 版本支持 Plugin Pages 功能（v4.23+），并刷新页面重试。</p>`;
    main.prepend(div);
  }
}

async function init() {
  if (!bridge) {
    logError('window.AstrBotPluginPage is not available');
    showInitError('Bridge SDK 未加载 (window.AstrBotPluginPage 未定义)');
    return;
  }

  try {
    pluginContext = await bridge.ready();
    bridgeReady = true;
    log('Bridge ready, context:', pluginContext);
  } catch (e) {
    logError('bridge.ready() failed:', e);
    showInitError(`Bridge 初始化失败: ${e.message || e}`);
    return;
  }

  try {
    initRouter();
    initDashboard();
    initSearch();
    initExport();
    initImport();
    initModal();
    initNavToggle();
    navigateToDefault();
  } catch (e) {
    logError('init failed:', e);
    showInitError(`初始化失败: ${e.message || e}`);
  }
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
    const statsResult = await apiGet('stats');
    if (statsResult.success) {
      updateStatsCards(statsResult.data);
      updatePlatformChart(statsResult.data.platform_stats);
    } else {
      logError('Failed to load stats:', statsResult.error);
    }
    const timelineResult = await apiGet('stats/timeline', { interval: 'day' });
    if (timelineResult.success) {
      updateTimelineChart(timelineResult.data.points);
    } else {
      logError('Failed to load timeline:', timelineResult.error);
    }
    updateTimeRangeDisplay(currentTimeRange);
    await loadRankingData();
  } finally {
    hideLoading();
  }
}

async function loadRankingData() {
  const senderResult = await apiGet('stats/senders', { limit: 10, time: currentTimeRange });
  if (senderResult.success) updateSenderChart(senderResult.data.senders);

  const groupResult = await apiGet('stats/groups', { limit: 10, time: currentTimeRange });
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
  const result = await apiGet('platforms');
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
  const result = await apiGet('groups', { platform, limit: 100 });
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
  const result = await apiGet('senders', { platform, limit: 100 });
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

    const result = await apiGet('messages', searchFilters);
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
  const result = await apiGet('message/detail', { id: messageId });
  hideLoading();
  if (!result.success) { showModal(`<p class="text-muted">加载失败: ${escapeHtml(result.error)}</p>`); return; }

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
      ${msg.message_chain.map(c => `<div class="chain-item"><span class="chain-type">${c.type}</span>${c.text ? escapeHtml(c.text) : ''}${c.url ? `<a href="${escapeHtml(c.url)}" target="_blank">[链接]</a>` : ''}${c.local_path ? `<span class="chain-media">[本地文件: ${escapeHtml(c.local_path)}]</span>` : ''}</div>`).join('')}
    </div>` : ''}
    ${msg.raw_message ? `
    <div class="detail-section mt-2">
      <h4>原始消息</h4>
      <pre class="raw-message">${escapeHtml(typeof msg.raw_message === 'string' ? msg.raw_message : JSON.stringify(msg.raw_message, null, 2))}</pre>
    </div>` : ''}
    <div class="detail-actions mt-2">
      <button class="btn" onclick="showMessageContext(${messageId})">查看上下文</button>
    </div>
  `);
}

async function showMessageContext(messageId) {
  showLoading();
  const result = await apiGet('message/context', { id: messageId, before: 5, after: 5 });
  hideLoading();
  if (!result.success) { showModal(`<p class="text-muted">加载失败: ${escapeHtml(result.error)}</p>`); return; }

  const data = result.data;
  const allMsgs = [...(data.before || []), data.target, ...(data.after || [])].filter(Boolean);
  showModal(`
    <div class="detail-section">
      <h4>消息上下文</h4>
      <div class="context-messages">
        ${allMsgs.map(m => `
          <div class="context-msg ${m.id === messageId ? 'context-target' : ''}">
            <span class="context-time">${formatShortTime(m.timestamp)}</span>
            <span class="context-sender">${escapeHtml(m.sender_name || m.sender_id)}</span>
            <span class="context-content">${escapeHtml(truncate(m.message_str, 100)) || '[非文本]'}</span>
          </div>
        `).join('')}
      </div>
    </div>
  `);
}

// ========== Export ==========

let exportFilters = {};
let selectedExportFormat = 'json';

function initExport() {
  document.querySelectorAll('.format-option').forEach(opt => {
    opt.addEventListener('click', () => {
      document.querySelectorAll('.format-option').forEach(o => o.classList.remove('selected'));
      opt.classList.add('selected');
      selectedExportFormat = opt.dataset.format;
    });
  });

  document.getElementById('includeMedia')?.addEventListener('change', (e) => {
    document.getElementById('mediaNote').style.display = e.target.checked ? 'block' : 'none';
  });

  document.getElementById('startExport')?.addEventListener('click', startExport);
}

async function loadExportData() {
  await loadPlatforms();
  displayExportFilters();
}

function displayExportFilters() {
  const el = document.getElementById('currentFilters');
  if (!el) return;
  const parts = [];
  if (exportFilters.keyword) parts.push(`关键词: ${exportFilters.keyword}`);
  if (exportFilters.platform) parts.push(`平台: ${exportFilters.platform}`);
  if (exportFilters.message_type) parts.push(`类型: ${exportFilters.message_type === 'group' ? '群聊' : '私聊'}`);
  el.innerHTML = parts.length ? `<div class="filter-tags">${parts.map(p => `<span class="filter-tag">${p}</span>`).join('')}</div>` : '<p class="text-muted">无筛选条件，将导出全部消息</p>';
}

async function startExport() {
  const filters = {
    time: document.getElementById('exportTime')?.value || undefined,
    platform: document.getElementById('exportPlatform')?.value || undefined,
    message_type: document.getElementById('exportType')?.value || undefined,
    start_time: document.getElementById('exportStartTime')?.value ? new Date(document.getElementById('exportStartTime').value).getTime() : undefined,
    end_time: document.getElementById('exportEndTime')?.value ? new Date(document.getElementById('exportEndTime').value).getTime() : undefined,
    keyword: document.getElementById('exportKeyword')?.value?.trim() || undefined,
    ...exportFilters,
  };

  Object.keys(filters).forEach(k => filters[k] === undefined && delete filters[k]);

  const options = {
    include_chain: document.getElementById('includeChain')?.checked ?? true,
    include_raw: document.getElementById('includeRaw')?.checked ?? false,
    include_media: document.getElementById('includeMedia')?.checked ?? false,
  };

  const result = await apiPost('export', { format: selectedExportFormat, filters, options });
  if (!result.success) {
    alert('导出失败: ' + result.error);
    return;
  }

  const task = result.data;
  document.getElementById('startExport').disabled = true;
  pollExportStatus(task.task_id);
}

async function pollExportStatus(taskId) {
  const progressEl = document.getElementById('exportProgress');
  if (progressEl) {
    progressEl.style.display = 'block';
    progressEl.innerHTML = '<p>导出中，请稍候...</p>';
  }

  const poll = async () => {
    const result = await apiGet('export/status', { task_id: taskId });
    if (!result.success) {
      if (progressEl) progressEl.innerHTML = `<p class="text-muted">查询状态失败: ${escapeHtml(result.error)}</p>`;
      document.getElementById('startExport').disabled = false;
      return;
    }

    const task = result.data;
    if (task.status === 'completed') {
      if (progressEl) progressEl.innerHTML = `<p>✅ 导出完成！共 ${task.actual_count || 0} 条记录</p><a href="#" id="downloadLink" class="btn btn-success">下载文件</a>`;
      document.getElementById('downloadLink')?.addEventListener('click', (e) => {
        e.preventDefault();
        downloadExportFile(taskId);
      });
      document.getElementById('startExport').disabled = false;
    } else if (task.status === 'failed') {
      if (progressEl) progressEl.innerHTML = `<p class="text-muted">❌ 导出失败: ${escapeHtml(task.error)}</p>`;
      document.getElementById('startExport').disabled = false;
    } else {
      if (progressEl) progressEl.innerHTML = `<p>导出中... (状态: ${task.status})</p>`;
      setTimeout(poll, 2000);
    }
  };

  await poll();
}

async function downloadExportFile(taskId) {
  if (bridge && bridgeReady) {
    try {
      await bridge.download('export/download', { task_id: taskId });
    } catch (e) {
      logError('download failed:', e);
      alert('下载失败: ' + (e.message || e));
    }
  } else {
    alert('Bridge SDK 未就绪，无法下载');
  }
}

// ========== Import ==========

let selectedFile = null;
let importMode = 'merge';

function initImport() {
  const uploadArea = document.getElementById('uploadArea');
  const fileInput = document.getElementById('importFile');

  uploadArea?.addEventListener('click', () => fileInput?.click());
  uploadArea?.addEventListener('dragover', (e) => { e.preventDefault(); uploadArea.classList.add('drag-over'); });
  uploadArea?.addEventListener('dragleave', () => uploadArea.classList.remove('drag-over'));
  uploadArea?.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('drag-over');
    if (e.dataTransfer.files.length) handleFileSelect(e.dataTransfer.files[0]);
  });
  fileInput?.addEventListener('change', () => {
    if (fileInput.files.length) handleFileSelect(fileInput.files[0]);
  });

  document.querySelectorAll('input[name="importMode"]').forEach(r => {
    r.addEventListener('change', () => { importMode = r.value; });
  });

  document.getElementById('startImport')?.addEventListener('click', startImport);
}

function handleFileSelect(file) {
  selectedFile = file;
  const infoEl = document.getElementById('fileInfo');
  if (infoEl) {
    infoEl.style.display = 'block';
    infoEl.innerHTML = `<p>已选择: <strong>${escapeHtml(file.name)}</strong> (${formatFileSize(file.size)})</p>`;
  }
}

async function startImport() {
  if (!selectedFile) {
    alert('请先选择文件');
    return;
  }

  const CHUNK_THRESHOLD = 50 * 1024 * 1024;
  const progressEl = document.getElementById('importProgress');
  if (progressEl) {
    progressEl.style.display = 'block';
    progressEl.innerHTML = '<p>导入中，请稍候...</p>';
  }
  document.getElementById('startImport').disabled = true;

  try {
    if (selectedFile.size > CHUNK_THRESHOLD) {
      await chunkedImport(selectedFile, importMode, progressEl);
    } else {
      await simpleImport(selectedFile, importMode, progressEl);
    }
  } catch (e) {
    logError('import failed:', e);
    if (progressEl) progressEl.innerHTML = `<p class="text-muted">❌ 导入失败: ${escapeHtml(e.message || e)}</p>`;
    document.getElementById('startImport').disabled = false;
  }
}

async function simpleImport(file, mode, progressEl) {
  if (!bridge || !bridgeReady) {
    throw new Error('Bridge SDK 未就绪');
  }

  const result = await bridge.upload('import/upload', file);
  log('simple import result:', result);

  if (progressEl) progressEl.innerHTML = '<p>文件上传完成，处理中...</p>';

  const taskId = result.data?.task_id || result.task_id;
  if (taskId) {
    pollImportStatus(taskId, progressEl);
  } else {
    if (progressEl) progressEl.innerHTML = `<p>✅ 导入完成</p>`;
    document.getElementById('startImport').disabled = false;
  }
}

async function chunkedImport(file, mode, progressEl) {
  if (!bridge || !bridgeReady) {
    throw new Error('Bridge SDK 未就绪');
  }

  const initResult = await apiPost('import/init', {
    filename: file.name,
    file_size: file.size,
    mode: mode,
  });
  if (!initResult.success) throw new Error(initResult.error);

  const { session_id, total_chunks, chunk_size } = initResult.data;
  if (progressEl) progressEl.innerHTML = `<p>分片上传中 (0/${total_chunks})...</p>`;

  for (let i = 0; i < total_chunks; i++) {
    const start = i * chunk_size;
    const end = Math.min(start + chunk_size, file.size);
    const chunk = file.slice(start, end);

    const chunkResult = await bridge.upload(`import/chunk?session_id=${session_id}&chunk_index=${i}`, chunk);
    log(`chunk ${i} result:`, chunkResult);

    if (progressEl) progressEl.innerHTML = `<p>分片上传中 (${i + 1}/${total_chunks})...</p>`;
  }

  const completeResult = await apiPost('import/complete', { session_id });
  if (!completeResult.success) throw new Error(completeResult.error);

  const taskId = completeResult.data?.task_id;
  if (taskId) {
    pollImportStatus(taskId, progressEl);
  } else {
    if (progressEl) progressEl.innerHTML = `<p>✅ 导入完成</p>`;
    document.getElementById('startImport').disabled = false;
  }
}

async function pollImportStatus(taskId, progressEl) {
  const poll = async () => {
    const result = await apiGet('import/status', { task_id: taskId });
    if (!result.success) {
      if (progressEl) progressEl.innerHTML = `<p class="text-muted">查询状态失败: ${escapeHtml(result.error)}</p>`;
      document.getElementById('startImport').disabled = false;
      return;
    }

    const task = result.data;
    if (task.status === 'completed') {
      if (progressEl) progressEl.innerHTML = `<p>✅ 导入完成！共导入 ${task.imported || 0} 条，跳过 ${task.skipped || 0} 条</p>`;
      document.getElementById('startImport').disabled = false;
    } else if (task.status === 'failed') {
      if (progressEl) progressEl.innerHTML = `<p class="text-muted">❌ 导入失败: ${escapeHtml(task.error)}</p>`;
      document.getElementById('startImport').disabled = false;
    } else {
      const processed = task.processed || 0;
      const total = task.total_records || '?';
      if (progressEl) progressEl.innerHTML = `<p>导入中... (${processed}/${total})</p>`;
      setTimeout(poll, 2000);
    }
  };

  await poll();
}

init();
