/**
 * 消息记录器 API 封装
 * 认证由 MultiWebManager 插件统一处理，本插件无需处理认证
 */

class MessageRecorderAPI {
  constructor(baseUrl = '/message_recorder/api') {
    this.baseUrl = baseUrl;
  }

  async request(url, options = {}) {
    const fullUrl = url.startsWith('http') ? url : this.baseUrl + url;
    options.headers = {
      'Content-Type': 'application/json',
      ...options.headers
    };

    try {
      const response = await fetch(fullUrl, options);
      const data = await response.json();
      return data;
    } catch (error) {
      console.error('API 请求失败:', error);
      return { success: false, error: error.message };
    }
  }

  // ========== 统计 API ==========

  async getStats() {
    return this.request('/stats');
  }

  async getTimeline(interval = 'day', filters = {}) {
    const params = new URLSearchParams({ interval });
    if (filters.platform) params.append('platform', filters.platform);
    if (filters.group_id) params.append('group_id', filters.group_id);
    if (filters.start_time) params.append('start_time', filters.start_time);
    if (filters.end_time) params.append('end_time', filters.end_time);
    return this.request(`/stats/timeline?${params}`);
  }

  async getSenderRanking(limit = 20, filters = {}) {
    const params = new URLSearchParams({ limit });
    if (filters.time) params.append('time', filters.time);
    if (filters.platform) params.append('platform', filters.platform);
    if (filters.group_id) params.append('group_id', filters.group_id);
    return this.request(`/stats/senders?${params}`);
  }

  async getGroupRanking(limit = 20, filters = {}) {
    const params = new URLSearchParams({ limit });
    if (filters.time) params.append('time', filters.time);
    if (filters.platform) params.append('platform', filters.platform);
    return this.request(`/stats/groups?${params}`);
  }

  // ========== 消息查询 API ==========

  async getMessages(filters = {}) {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== null && value !== undefined && value !== '') {
        params.append(key, value);
      }
    });
    return this.request(`/messages?${params}`);
  }

  async getMessageDetail(id) {
    return this.request(`/messages/${id}`);
  }

  async getMessageContext(id, before = 5, after = 5) {
    const params = new URLSearchParams({ before, after });
    return this.request(`/messages/${id}/context?${params}`);
  }

  // ========== 搜索 API ==========

  async search(keyword, filters = {}) {
    const params = new URLSearchParams({ keyword });
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== null && value !== undefined && value !== '' && key !== 'keyword') {
        params.append(key, value);
      }
    });
    return this.request(`/search?${params}`);
  }

  // ========== 导出 API ==========

  async createExport(format, filters = {}, options = {}) {
    return this.request('/export', {
      method: 'POST',
      body: JSON.stringify({ format, filters, options })
    });
  }

  async getExportStatus(taskId) {
    return this.request(`/export/status/${taskId}`);
  }

  getExportDownloadUrl(taskId) {
    return `${this.baseUrl}/export/download/${taskId}`;
  }

  // ========== 导入 API ==========

  async createImport(file, mode = 'merge') {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('mode', mode);

    return this.request('/import', {
      method: 'POST',
      body: formData,
      headers: {} // 不设置 Content-Type，让浏览器自动设置
    });
  }

  async getImportStatus(taskId) {
    return this.request(`/import/status/${taskId}`);
  }

  // ========== 元数据 API ==========

  async getPlatforms() {
    return this.request('/platforms');
  }

  async getSenders(filters = {}) {
    const params = new URLSearchParams();
    if (filters.platform) params.append('platform', filters.platform);
    if (filters.group_id) params.append('group_id', filters.group_id);
    if (filters.limit) params.append('limit', filters.limit);
    return this.request(`/senders?${params}`);
  }

  async getGroups(filters = {}) {
    const params = new URLSearchParams();
    if (filters.platform) params.append('platform', filters.platform);
    if (filters.limit) params.append('limit', filters.limit);
    return this.request(`/groups?${params}`);
  }
}

// 创建全局 API 实例
const api = new MessageRecorderAPI();