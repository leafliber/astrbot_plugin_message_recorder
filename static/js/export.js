/**
 * 导出导入页面逻辑
 */

// ========== 导出页面 ==========

let selectedFormat = 'json';
let exportFilters = {};

// 初始化导出页面
async function initExportPage() {
  // 从 URL 参数获取筛选条件
  const urlParams = new URLSearchParams(window.location.search);
  const filtersStr = urlParams.get('filters');
  if (filtersStr) {
    try {
      exportFilters = JSON.parse(filtersStr);
      // 显示筛选条件
      displayExportFilters();
    } catch (e) {
      console.error('解析筛选条件失败:', e);
    }
  }

  // 加载平台列表
  await loadExportPlatforms();

  // 绑定格式选择事件
  bindFormatSelection();

  // 绑定筛选事件
  bindExportFilterEvents();

  // 绑定导出按钮
  bindExportButton();
}

function displayExportFilters() {
  // 显示当前筛选条件
  const container = document.getElementById('currentFilters');
  if (!container) return;

  let html = '<p>当前筛选条件:</p><ul>';
  Object.entries(exportFilters).forEach(([key, value]) => {
    if (value) {
      html += `<li><strong>${key}</strong>: ${value}</li>`;
    }
  });
  html += '</ul>';
  container.innerHTML = html;
}

async function loadExportPlatforms() {
  const result = await api.getPlatforms();
  if (!result.success) return;

  const platformSelect = document.getElementById('exportPlatform');
  if (!platformSelect) return;

  platformSelect.innerHTML = '<option value="">全部平台</option>';
  result.data.platforms.forEach(platform => {
    const option = document.createElement('option');
    option.value = platform;
    option.textContent = getPlatformIcon(platform);
    platformSelect.appendChild(option);
  });

  // 设置已选值
  if (exportFilters.platform) {
    platformSelect.value = exportFilters.platform;
  }
}

function bindFormatSelection() {
  const formatOptions = document.querySelectorAll('.format-option');
  formatOptions.forEach(option => {
    option.addEventListener('click', () => {
      formatOptions.forEach(o => o.classList.remove('selected'));
      option.classList.add('selected');
      selectedFormat = option.dataset.format;
    });
  });

  // 默认选中 JSON
  const defaultOption = document.querySelector('.format-option[data-format="json"]');
  if (defaultOption) {
    defaultOption.classList.add('selected');
  }
}

function bindExportFilterEvents() {
  // 时间范围选择
  const timeSelect = document.getElementById('exportTime');
  if (timeSelect) {
    timeSelect.addEventListener('change', () => {
      if (timeSelect.value) {
        exportFilters.time = timeSelect.value;
        delete exportFilters.start_time;
        delete exportFilters.end_time;
      } else {
        delete exportFilters.time;
      }
    });
  }

  // 自定义时间范围
  const startTimeInput = document.getElementById('exportStartTime');
  const endTimeInput = document.getElementById('exportEndTime');
  if (startTimeInput && endTimeInput) {
    startTimeInput.addEventListener('change', () => {
      if (startTimeInput.value) {
        exportFilters.start_time = new Date(startTimeInput.value).getTime();
        delete exportFilters.time;
      }
    });
    endTimeInput.addEventListener('change', () => {
      if (endTimeInput.value) {
        exportFilters.end_time = new Date(endTimeInput.value).getTime();
        delete exportFilters.time;
      }
    });
  }

  // 平台选择
  const platformSelect = document.getElementById('exportPlatform');
  if (platformSelect) {
    platformSelect.addEventListener('change', () => {
      if (platformSelect.value) {
        exportFilters.platform = platformSelect.value;
      } else {
        delete exportFilters.platform;
      }
    });
  }

  // 消息类型
  const typeSelect = document.getElementById('exportType');
  if (typeSelect) {
    typeSelect.addEventListener('change', () => {
      if (typeSelect.value) {
        exportFilters.message_type = typeSelect.value;
      } else {
        delete exportFilters.message_type;
      }
    });
  }

  // 关键词
  const keywordInput = document.getElementById('exportKeyword');
  if (keywordInput) {
    keywordInput.addEventListener('input', () => {
      if (keywordInput.value.trim()) {
        exportFilters.keyword = keywordInput.value.trim();
      } else {
        delete exportFilters.keyword;
      }
    });
  }
}

function bindExportButton() {
  const exportBtn = document.getElementById('startExport');
  if (exportBtn) {
    exportBtn.addEventListener('click', startExport);
  }
}

async function startExport() {
  const options = {
    include_chain: document.getElementById('includeChain')?.checked ?? true,
    include_raw: document.getElementById('includeRaw')?.checked ?? false
  };

  showLoading();
  const result = await api.createExport(selectedFormat, exportFilters, options);
  hideLoading();

  if (!result.success) {
    alert('创建导出任务失败: ' + result.error);
    return;
  }

  // 显示任务进度
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
      <div class="task-progress">
        <div class="progress-bar" id="exportProgressBar" style="width: 0%"></div>
      </div>
      <p class="task-status" id="exportTaskStatus">准备中...</p>
      <button class="btn btn-success hidden" id="downloadBtn" onclick="downloadExport('${task.task_id}')">
        下载文件
      </button>
    </div>
  `;

  // 开始轮询任务状态
  pollExportStatus(task.task_id);
}

async function pollExportStatus(taskId) {
  const statusEl = document.getElementById('exportTaskStatus');
  const progressEl = document.getElementById('exportProgressBar');
  const downloadBtn = document.getElementById('downloadBtn');

  let status = 'pending';
  while (status !== 'completed' && status !== 'failed') {
    await new Promise(resolve => setTimeout(resolve, 1000));

    const result = await api.getExportStatus(taskId);
    if (!result.success) break;

    status = result.data.status;

    if (statusEl) {
      const statusText = {
        'pending': '准备中...',
        'processing': '处理中...',
        'completed': '已完成!',
        'failed': '失败'
      };
      statusEl.textContent = statusText[status] || status;
    }

    if (progressEl) {
      if (status === 'completed') {
        progressEl.style.width = '100%';
      } else if (status === 'processing') {
        progressEl.style.width = '50%';
      }
    }

    if (downloadBtn && status === 'completed') {
      downloadBtn.classList.remove('hidden');
      downloadBtn.dataset.taskId = taskId;
    }
  }
}

function downloadExport(taskId) {
  const url = api.getExportDownloadUrl(taskId);
  window.open(url, '_blank');
}

// ========== 导入页面 ==========

let selectedImportMode = 'merge';

// 初始化导入页面
function initImportPage() {
  // 绑定文件上传
  bindFileUpload();

  // 绑定导入模式选择
  bindImportModeSelection();

  // 绑定导入按钮
  bindImportButton();
}

function bindFileUpload() {
  const uploadArea = document.getElementById('uploadArea');
  const fileInput = document.getElementById('importFile');
  const fileInfo = document.getElementById('fileInfo');

  if (!uploadArea || !fileInput) return;

  // 点击上传区域触发文件选择
  uploadArea.addEventListener('click', () => {
    fileInput.click();
  });

  // 拖拽上传
  uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.classList.add('dragover');
  });

  uploadArea.addEventListener('dragleave', () => {
    uploadArea.classList.remove('dragover');
  });

  uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('dragover');

    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFileSelect(files[0]);
    }
  });

  // 文件选择
  fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
      handleFileSelect(fileInput.files[0]);
    }
  });
}

function handleFileSelect(file) {
  const fileInfo = document.getElementById('fileInfo');
  if (!fileInfo) return;

  // 检查文件格式
  const validFormats = ['.json', '.csv'];
  const fileExt = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
  if (!validFormats.includes(fileExt)) {
    alert('请选择 JSON 或 CSV 格式的文件');
    return;
  }

  fileInfo.style.display = 'block';
  fileInfo.innerHTML = `
    <p>已选择文件: <strong>${file.name}</strong></p>
    <p>文件大小: ${formatFileSize(file.size)}</p>
  `;

  // 存储文件引用
  window.selectedImportFile = file;
}

function formatFileSize(size) {
  if (size < 1024) return size + ' B';
  if (size < 1024 * 1024) return (size / 1024).toFixed(1) + ' KB';
  return (size / (1024 * 1024)).toFixed(1) + ' MB';
}

function bindImportModeSelection() {
  const modeRadios = document.querySelectorAll('input[name="importMode"]');
  modeRadios.forEach(radio => {
    radio.addEventListener('change', () => {
      selectedImportMode = radio.value;
    });
  });
}

function bindImportButton() {
  const importBtn = document.getElementById('startImport');
  if (importBtn) {
    importBtn.addEventListener('click', startImport);
  }
}

async function startImport() {
  if (!window.selectedImportFile) {
    alert('请先选择要导入的文件');
    return;
  }

  showLoading();
  const result = await api.createImport(window.selectedImportFile, selectedImportMode);
  hideLoading();

  if (!result.success) {
    alert('创建导入任务失败: ' + result.error);
    return;
  }

  // 显示任务进度
  showImportProgress(result.data);
}

function showImportProgress(task) {
  const container = document.getElementById('importProgress');
  if (!container) return;

  container.style.display = 'block';
  container.innerHTML = `
    <div class="card">
      <h3>导入任务 #${task.task_id}</h3>
      <p>文件: ${task.filename}</p>
      <p>模式: ${task.mode === 'merge' ? '合并' : task.mode === 'skip_duplicates' ? '跳过重复' : '替换'}</p>
      <div class="task-stats">
        <div class="task-stat">
          <div class="task-stat-value" id="importProcessed">0</div>
          <div class="task-stat-label">已处理</div>
        </div>
        <div class="task-stat">
          <div class="task-stat-value" id="importImported">0</div>
          <div class="task-stat-label">已导入</div>
        </div>
        <div class="task-stat">
          <div class="task-stat-value" id="importSkipped">0</div>
          <div class="task-stat-label">已跳过</div>
        </div>
        <div class="task-stat">
          <div class="task-stat-value" id="importErrors">0</div>
          <div class="task-stat-label">错误</div>
        </div>
      </div>
      <div class="task-progress">
        <div class="progress-bar" id="importProgressBar" style="width: 0%"></div>
      </div>
      <p class="task-status" id="importTaskStatus">准备中...</p>
    </div>
  `;

  // 开始轮询任务状态
  pollImportStatus(task.task_id);
}

async function pollImportStatus(taskId) {
  const statusEl = document.getElementById('importTaskStatus');
  const progressEl = document.getElementById('importProgressBar');
  const processedEl = document.getElementById('importProcessed');
  const importedEl = document.getElementById('importImported');
  const skippedEl = document.getElementById('importSkipped');
  const errorsEl = document.getElementById('importErrors');

  let status = 'pending';
  while (status !== 'completed' && status !== 'failed') {
    await new Promise(resolve => setTimeout(resolve, 500));

    const result = await api.getImportStatus(taskId);
    if (!result.success) break;

    const task = result.data;
    status = task.status;

    if (statusEl) {
      const statusText = {
        'pending': '准备中...',
        'processing': '处理中...',
        'completed': '已完成!',
        'failed': '失败: ' + (task.error || '')
      };
      statusEl.textContent = statusText[status] || status;
    }

    // 更新统计数据
    if (processedEl) processedEl.textContent = task.processed || 0;
    if (importedEl) importedEl.textContent = task.imported || 0;
    if (skippedEl) skippedEl.textContent = task.skipped || 0;
    if (errorsEl) errorsEl.textContent = task.errors || 0;

    // 更新进度条
    if (progressEl && task.total_records > 0) {
      const percent = Math.round((task.processed / task.total_records) * 100);
      progressEl.style.width = percent + '%';
    }
  }
}

// ========== 页面初始化 ==========

document.addEventListener('DOMContentLoaded', () => {
  // 判断是导出还是导入页面
  if (document.getElementById('exportPage')) {
    initExportPage();
  }
  if (document.getElementById('importPage')) {
    initImportPage();
  }
});