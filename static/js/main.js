/**
 * 主脚本 - 公共功能
 */

// ========== 导航栏切换 ==========

document.getElementById('navToggle')?.addEventListener('click', () => {
  const navLinks = document.getElementById('navLinks');
  navLinks?.classList.toggle('show');
});

// ========== 模态框控制 ==========

const modal = document.getElementById('messageModal');
const modalClose = document.getElementById('modalClose');
const modalBody = document.getElementById('modalBody');

function showModal(content) {
  if (modalBody) {
    modalBody.innerHTML = content;
  }
  modal?.classList.add('show');
}

function hideModal() {
  modal?.classList.remove('show');
}

modalClose?.addEventListener('click', hideModal);
modal?.addEventListener('click', (e) => {
  if (e.target === modal) {
    hideModal();
  }
});

// ========== 加载指示器 ==========

const loadingOverlay = document.getElementById('loadingOverlay');

function showLoading() {
  if (loadingOverlay) {
    loadingOverlay.style.display = 'flex';
  }
}

function hideLoading() {
  if (loadingOverlay) {
    loadingOverlay.style.display = 'none';
  }
}

// ========== 工具函数 ==========

function formatTime(timestamp) {
  const date = new Date(timestamp);
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
}

function formatShortTime(timestamp) {
  const date = new Date(timestamp);
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
}

function getPlatformIcon(platform) {
  const icons = {
    'telegram': 'TG',
    'discord': 'DC',
    'qq_official': 'QQ',
    'qq_private': 'QQ',
    'wechat': 'WX'
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

// ========== 消息详情展示 ==========

async function showMessageDetail(messageId) {
  showLoading();
  const result = await api.getMessageDetail(messageId);
  hideLoading();

  if (!result.success) {
    showModal(`<p class="text-muted">加载失败: ${result.error}</p>`);
    return;
  }

  const msg = result.data;
  const content = `
    <div class="detail-section">
      <div class="detail-row">
        <span class="detail-label">时间:</span>
        <span class="detail-value">${formatTime(msg.timestamp)}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">平台:</span>
        <span class="detail-value">${getPlatformIcon(msg.platform)}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">发送者:</span>
        <span class="detail-value">${escapeHtml(msg.sender_name || msg.sender_id)}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">消息类型:</span>
        <span class="detail-value">${msg.message_type === 'group' ? '群聊' : '私聊'}</span>
      </div>
      ${msg.group_id ? `
      <div class="detail-row">
        <span class="detail-label">群组:</span>
        <span class="detail-value">${escapeHtml(msg.group_id)}</span>
      </div>
      ` : ''}
      <div class="detail-row">
        <span class="detail-label">内容:</span>
        <span class="detail-value">${escapeHtml(msg.message_str) || '[非文本消息]'}</span>
      </div>
    </div>
    ${msg.message_chain && msg.message_chain.length > 0 ? `
    <div class="detail-section mt-2">
      <h4>消息链</h4>
      <pre style="background: #f5f6fa; padding: 0.5rem; border-radius: 4px; overflow-x: auto; font-size: 0.85rem;">
${escapeHtml(JSON.stringify(msg.message_chain, null, 2))}
      </pre>
    </div>
    ` : ''}
    <div class="message-actions mt-2">
      <a href="#" onclick="showMessageContext(${msg.id}); return false;">查看上下文</a>
    </div>
  `;
  showModal(content);
}

async function showMessageContext(messageId) {
  showLoading();
  const result = await api.getMessageContext(messageId);
  hideLoading();

  if (!result.success) {
    showModal(`<p class="text-muted">加载失败: ${result.error}</p>`);
    return;

  }

  const data = result.data;
  let content = '<h4>上下文消息</h4>';

  // 前文消息
  if (data.before && data.before.length > 0) {
    content += '<div class="mb-2"><strong>前文:</strong></div>';
    data.before.forEach(msg => {
      content += `
        <div class="context-message">
          <span class="text-muted">${formatShortTime(msg.timestamp)}</span>
          <strong>${escapeHtml(msg.sender_name || msg.sender_id)}</strong>:
          ${escapeHtml(truncate(msg.message_str))}
        </div>
      `;
    });
  }

  // 目标消息
  content += `
    <div class="context-message highlight">
      <span class="text-muted">${formatShortTime(data.target.timestamp)}</span>
      <strong>${escapeHtml(data.target.sender_name || data.target.sender_id)}</strong>:
      ${escapeHtml(data.target.message_str) || '[非文本消息]'}
    </div>
  `;

  // 后文消息
  if (data.after && data.after.length > 0) {
    content += '<div class="mb-2 mt-2"><strong>后文:</strong></div>';
    data.after.forEach(msg => {
      content += `
        <div class="context-message">
          <span class="text-muted">${formatShortTime(msg.timestamp)}</span>
          <strong>${escapeHtml(msg.sender_name || msg.sender_id)}</strong>:
          ${escapeHtml(truncate(msg.message_str))}
        </div>
      `;
    });
  }

  showModal(content);
}