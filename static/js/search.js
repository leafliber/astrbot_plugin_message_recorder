/**
 * 搜索页面逻辑
 */

// 当前状态
let currentFilters = {
  limit: 50,
  offset: 0,
  order: 'desc'
};
let totalMessages = 0;

// ========== 初始化 ==========

document.addEventListener('DOMContentLoaded', async () => {
  // 加载平台列表
  await loadPlatforms();

  // 绑定搜索事件
  bindSearchEvents();

  // 加载初始数据
  await loadMessages();
});

// ========== 加载平台列表 ==========

async function loadPlatforms() {
  const result = await api.getPlatforms();
  if (!result.success) return;

  const platformSelect = document.getElementById('platformFilter');
  if (!platformSelect) return;

  // 清空并添加选项
  platformSelect.innerHTML = '<option value="">全部平台</option>';
  result.data.platforms.forEach(platform => {
    const option = document.createElement('option');
    option.value = platform;
    option.textContent = getPlatformIcon(platform);
    platformSelect.appendChild(option);
  });
}

// ========== 绑定搜索事件 ==========

function bindSearchEvents() {
  // 关键词搜索（防抖）
  const keywordInput = document.getElementById('keywordInput');
  if (keywordInput) {
    let debounceTimer;
    keywordInput.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        currentFilters.keyword = keywordInput.value.trim();
        currentFilters.offset = 0;
        loadMessages();
      }, 300);
    });
  }

  // 筛选条件变化
  const platformFilter = document.getElementById('platformFilter');
  if (platformFilter) {
    platformFilter.addEventListener('change', () => {
      currentFilters.platform = platformFilter.value;
      currentFilters.offset = 0;
      loadMessages();
    });
  }

  const typeFilter = document.getElementById('typeFilter');
  if (typeFilter) {
    typeFilter.addEventListener('change', () => {
      currentFilters.message_type = typeFilter.value;
      currentFilters.offset = 0;
      loadMessages();
    });
  }

  const orderFilter = document.getElementById('orderFilter');
  if (orderFilter) {
    orderFilter.addEventListener('change', () => {
      currentFilters.order = orderFilter.value;
      currentFilters.offset = 0;
      loadMessages();
    });
  }

  const limitFilter = document.getElementById('limitFilter');
  if (limitFilter) {
    limitFilter.addEventListener('change', () => {
      currentFilters.limit = parseInt(limitFilter.value);
      currentFilters.offset = 0;
      loadMessages();
    });
  }

  // 群组/发送者筛选（当平台变化时更新）
  const groupFilter = document.getElementById('groupFilter');
  const senderFilter = document.getElementById('senderFilter');
  if (platformFilter && groupFilter) {
    platformFilter.addEventListener('change', async () => {
      await loadGroups(platformFilter.value);
      await loadSenders(platformFilter.value);
    });
  }
}

// ========== 加载群组/发送者列表 ==========

async function loadGroups(platform) {
  const result = await api.getGroups({ platform, limit: 100 });
  if (!result.success) return;

  const groupSelect = document.getElementById('groupFilter');
  if (!groupSelect) return;

  groupSelect.innerHTML = '<option value="">全部群组</option>';
  result.data.groups.forEach(group => {
    const option = document.createElement('option');
    option.value = group.id;
    option.textContent = truncate(group.id, 30);
    groupSelect.appendChild(option);
  });
}

async function loadSenders(platform) {
  const result = await api.getSenders({ platform, limit: 100 });
  if (!result.success) return;

  const senderSelect = document.getElementById('senderFilter');
  if (!senderSelect) return;

  senderSelect.innerHTML = '<option value="">全部发送者</option>';
  result.data.senders.forEach(sender => {
    const option = document.createElement('option');
    option.value = sender.id;
    option.textContent = truncate(sender.name, 30);
    senderSelect.appendChild(option);
  });
}

// ========== 加载消息 ==========

async function loadMessages() {
  showLoading();

  // 获取额外的筛选条件
  const groupFilter = document.getElementById('groupFilter');
  const senderFilter = document.getElementById('senderFilter');
  const startTimeInput = document.getElementById('startTimeInput');
  const endTimeInput = document.getElementById('endTimeInput');

  if (groupFilter && groupFilter.value) {
    currentFilters.group_id = groupFilter.value;
  } else {
    delete currentFilters.group_id;
  }

  if (senderFilter && senderFilter.value) {
    currentFilters.sender_id = senderFilter.value;
  } else {
    delete currentFilters.sender_id;
  }

  if (startTimeInput && startTimeInput.value) {
    currentFilters.start_time = new Date(startTimeInput.value).getTime();
  } else {
    delete currentFilters.start_time;
  }

  if (endTimeInput && endTimeInput.value) {
    currentFilters.end_time = new Date(endTimeInput.value).getTime();
  } else {
    delete currentFilters.end_time;
  }

  const result = await api.getMessages(currentFilters);
  hideLoading();

  if (!result.success) {
    showMessageError(result.error);
    return;
  }

  totalMessages = result.data.pagination.total;
  renderMessages(result.data.messages);
  renderPagination(result.data.pagination);
}

// ========== 渲染消息列表 ==========

function renderMessages(messages) {
  const container = document.getElementById('messageList');
  if (!container) return;

  if (messages.length === 0) {
    container.innerHTML = '<p class="text-center text-muted">暂无消息记录</p>';
    return;
  }

  container.innerHTML = messages.map(msg => `
    <div class="message-card" onclick="showMessageDetail(${msg.id})">
      <div class="message-header">
        <span class="message-time">${formatShortTime(msg.timestamp)}</span>
        <span class="message-platform">${getPlatformIcon(msg.platform)}</span>
        <span class="message-type">${msg.message_type === 'group' ? '群聊' : '私聊'}</span>
        <span class="message-sender">${escapeHtml(msg.sender_name || msg.sender_id)}</span>
      </div>
      <div class="message-content">${escapeHtml(truncate(msg.message_str, 200))}</div>
      <div class="message-actions">
        <a href="#" onclick="showMessageContext(${msg.id}); return false;">查看上下文</a>
      </div>
    </div>
  `).join('');
}

function showMessageError(error) {
  const container = document.getElementById('messageList');
  if (container) {
    container.innerHTML = `<p class="text-center text-muted">加载失败: ${escapeHtml(error)}</p>`;
  }
}

// ========== 渲染分页 ==========

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
    <button class="pagination-btn ${currentPage <= 1 ? 'disabled' : ''}"
            onclick="goToPage(${currentPage - 1})"
            ${currentPage <= 1 ? 'disabled' : ''}>
      上一页
    </button>
    <span class="pagination-info">第 ${currentPage}/${totalPages} 页，共 ${total} 条</span>
    <button class="pagination-btn ${currentPage >= totalPages ? 'disabled' : ''}"
            onclick="goToPage(${currentPage + 1})"
            ${currentPage >= totalPages ? 'disabled' : ''}>
      下一页
    </button>
  `;
}

function goToPage(page) {
  currentFilters.offset = (page - 1) * currentFilters.limit;
  loadMessages();
}

// ========== 导出功能 ==========

function exportCurrentResults() {
  // 获取当前筛选条件并跳转到导出页面
  const filters = JSON.stringify(currentFilters);
  window.location.href = `/message_recorder/export?filters=${encodeURIComponent(filters)}`;
}