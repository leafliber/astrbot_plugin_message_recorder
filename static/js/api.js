/**
 * 消息记录器 API 封装
 * 支持验证码鉴权机制
 */

class MessageRecorderAPI {
  constructor(baseUrl = '/message_recorder/api') {
    this.baseUrl = baseUrl;
    this.authToken = null;
    this.tokenExpires = 0;
  }

  async request(url, options = {}) {
    const fullUrl = url.startsWith('http') ? url : this.baseUrl + url;
    if (!options.skipContentType) {
      options.headers = {
        'Content-Type': 'application/json',
        ...options.headers
      };
    }
    delete options.skipContentType;

    if (this.authToken && Date.now() < this.tokenExpires) {
      options.headers = options.headers || {};
      options.headers['X-Auth-Token'] = this.authToken;
    }

    try {
      const response = await fetch(fullUrl, options);
      const data = await response.json();

      if (response.status === 401 && data.require_captcha) {
        const verified = await this.handleCaptchaAuth();
        if (verified) {
          options.headers = options.headers || {};
          options.headers['X-Auth-Token'] = this.authToken;
          const retryResponse = await fetch(fullUrl, options);
          return await retryResponse.json();
        }
        return { success: false, error: '验证码验证失败', require_captcha: true };
      }

      return data;
    } catch (error) {
      console.error('API 请求失败:', error);
      return { success: false, error: error.message };
    }
  }

  async handleCaptchaAuth() {
    const captchaData = await this.getCaptcha();
    if (!captchaData.success) {
      alert('获取验证码失败: ' + captchaData.error);
      return false;
    }

    const code = await this.showCaptchaDialog(captchaData.captcha_id);
    if (!code) {
      return false;
    }

    const verifyResult = await this.verifyCaptcha(captchaData.captcha_id, code);
    if (!verifyResult.success) {
      alert('验证码错误或已过期');
      return false;
    }

    this.authToken = verifyResult.auth_token;
    this.tokenExpires = Date.now() + (verifyResult.expires_in - 60) * 1000;
    return true;
  }

  showCaptchaDialog(captchaId) {
    return new Promise((resolve) => {
      const existing = document.getElementById('captcha-modal');
      if (existing) existing.remove();

      const modal = document.createElement('div');
      modal.id = 'captcha-modal';
      modal.innerHTML = `
        <div class="captcha-overlay" style="
          position: fixed; top: 0; left: 0; right: 0; bottom: 0;
          background: rgba(0,0,0,0.5); display: flex;
          align-items: center; justify-content: center; z-index: 10000;
        ">
          <div class="captcha-dialog" style="
            background: var(--bg-primary, #fff);
            padding: 2rem; border-radius: 8px;
            text-align: center; min-width: 320px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
          ">
            <h3 style="margin: 0 0 1rem 0;">安全验证</h3>
            <p style="margin: 0 0 0.5rem 0; color: var(--text-secondary, #666);">请查看 AstrBot 控制台日志获取验证码</p>
            <p style="margin: 0 0 1rem 0; font-size: 0.85rem; color: var(--text-secondary, #888);">验证码 ID: ${captchaId}</p>
            <input type="text" id="captcha-input" placeholder="请输入 6 位验证码" style="
              width: 100%; padding: 0.75rem;
              border: 1px solid var(--border-color, #ddd);
              border-radius: 4px; font-size: 1rem;
              text-align: center; letter-spacing: 0.25rem;
              box-sizing: border-box;
            " maxlength="6" autocomplete="off">
            <div style="margin-top: 1rem; display: flex; gap: 0.5rem;">
              <button id="captcha-cancel" style="
                flex: 1; padding: 0.75rem;
                border: 1px solid var(--border-color, #ddd);
                background: var(--bg-secondary, #f0f0f0);
                border-radius: 4px; cursor: pointer;
              ">取消</button>
              <button id="captcha-submit" style="
                flex: 1; padding: 0.75rem;
                border: none; background: #4CAF50;
                color: white; border-radius: 4px; cursor: pointer;
              ">确认</button>
            </div>
          </div>
        </div>
      `;

      document.body.appendChild(modal);

      const input = document.getElementById('captcha-input');
      const cancelBtn = document.getElementById('captcha-cancel');
      const submitBtn = document.getElementById('captcha-submit');

      const close = () => modal.remove();

      cancelBtn.addEventListener('click', () => {
        close();
        resolve(null);
      });

      submitBtn.addEventListener('click', () => {
        const value = input.value.trim();
        if (value.length === 6) {
          close();
          resolve(value);
        } else {
          input.style.borderColor = '#f44336';
          input.focus();
        }
      });

      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          submitBtn.click();
        }
      });

      input.focus();
    });
  }

  async getCaptcha() {
    return this.request('/captcha');
  }

  async verifyCaptcha(captchaId, code) {
    return this.request('/captcha/verify', {
      method: 'POST',
      body: JSON.stringify({ captcha_id: captchaId, code })
    });
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
      skipContentType: true
    });
  }

  async getImportStatus(taskId) {
    return this.request(`/import/status/${taskId}`);
  }

  async initChunkUpload(filename, fileSize, mode = 'merge') {
    return this.request('/import/chunk/init', {
      method: 'POST',
      body: JSON.stringify({ filename, file_size: fileSize, mode })
    });
  }

  async uploadChunk(sessionId, chunkIndex, chunkData) {
    const formData = new FormData();
    formData.append('session_id', sessionId);
    formData.append('chunk_index', chunkIndex);
    formData.append('chunk', chunkData);

    return this.request('/import/chunk/upload', {
      method: 'POST',
      body: formData,
      skipContentType: true
    });
  }

  async completeChunkUpload(sessionId) {
    return this.request('/import/chunk/complete', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId })
    });
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

const api = new MessageRecorderAPI();
