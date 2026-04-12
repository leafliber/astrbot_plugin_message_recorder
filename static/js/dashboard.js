/**
 * 仪表盘页面逻辑
 */

// ECharts 图表实例
let timelineChart = null;
let platformChart = null;
let senderChart = null;
let groupChart = null;

// 当前时间范围
let currentTimeRange = 'last30d';
let currentFilters = {};

// 时间范围名称映射
const timeRangeLabels = {
  'today': '今日',
  'yesterday': '昨日',
  'last7d': '最近7天',
  'last30d': '最近30天',
  'week': '本周',
  'month': '本月'
};

// ========== 初始化 ==========

document.addEventListener('DOMContentLoaded', async () => {
  // 初始化图表
  initCharts();

  // 加载统计数据
  await loadDashboardData();

  // 初始化时间范围显示
  updateTimeRangeDisplay(currentTimeRange);

  // 绑定时间选择器事件
  bindTimeSelectorEvents();
});

// ========== 图表初始化 ==========

function initCharts() {
  // 时间趋势图
  const timelineEl = document.getElementById('timelineChart');
  if (timelineEl) {
    timelineChart = echarts.init(timelineEl);
  }

  // 平台分布图
  const platformEl = document.getElementById('platformChart');
  if (platformEl) {
    platformChart = echarts.init(platformEl);
  }

  // 发送者排行图
  const senderEl = document.getElementById('senderChart');
  if (senderEl) {
    senderChart = echarts.init(senderEl);
  }

  // 群组排行图
  const groupEl = document.getElementById('groupChart');
  if (groupEl) {
    groupChart = echarts.init(groupEl);
  }

  // 窗口大小改变时重绘图表
  window.addEventListener('resize', () => {
    timelineChart?.resize();
    platformChart?.resize();
    senderChart?.resize();
    groupChart?.resize();
  });
}

// ========== 加载仪表盘数据 ==========

async function loadDashboardData() {
  showLoading();

  // 加载总体统计
  const statsResult = await api.getStats();
  if (statsResult.success) {
    updateStatsCards(statsResult.data);
    updatePlatformChart(statsResult.data.platform_stats);
  }

  // 加载时间趋势（不受时间范围选择器影响）
  const timelineResult = await api.getTimeline('day', {});
  if (timelineResult.success) {
    updateTimelineChart(timelineResult.data.points);
  }

  // 加载排行数据（受时间范围选择器影响）
  await loadRankingData();

  hideLoading();
}

async function loadRankingData() {
  // 加载发送者排行
  const senderResult = await api.getSenderRanking(10, currentFilters);
  if (senderResult.success) {
    updateSenderChart(senderResult.data.senders);
  }

  // 加载群组排行
  const groupResult = await api.getGroupRanking(10, currentFilters);
  if (groupResult.success) {
    updateGroupChart(groupResult.data.groups);
  }
}

// ========== 更新统计卡片 ==========

function updateStatsCards(stats) {
  const totalEl = document.getElementById('totalCount');
  const groupEl = document.getElementById('groupCount');
  const privateEl = document.getElementById('privateCount');
  const platformEl = document.getElementById('platformCount');

  if (totalEl) totalEl.textContent = formatNumber(stats.total_count);
  if (groupEl) groupEl.textContent = formatNumber(stats.group_message_count);
  if (privateEl) privateEl.textContent = formatNumber(stats.private_message_count);
  if (platformEl) platformEl.textContent = stats.platform_count;
}

function formatNumber(num) {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M';
  } else if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K';
  }
  return num.toString();
}

function formatTimestamp(ts) {
  const date = new Date(ts);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  const seconds = String(date.getSeconds()).padStart(2, '0');
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
}

function parseTimeRangeClient(timeRange) {
  const now = new Date();
  let start, end;

  switch (timeRange) {
    case 'today':
      start = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0);
      end = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59);
      break;
    case 'yesterday':
      const yesterday = new Date(now);
      yesterday.setDate(now.getDate() - 1);
      start = new Date(yesterday.getFullYear(), yesterday.getMonth(), yesterday.getDate(), 0, 0, 0);
      end = new Date(yesterday.getFullYear(), yesterday.getMonth(), yesterday.getDate(), 23, 59, 59);
      break;
    case 'last7d':
      start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
      end = now;
      break;
    case 'last30d':
      start = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
      end = now;
      break;
    case 'week':
      const dayOfWeek = now.getDay() || 7;
      const weekStart = new Date(now);
      weekStart.setDate(now.getDate() - dayOfWeek + 1);
      start = new Date(weekStart.getFullYear(), weekStart.getMonth(), weekStart.getDate(), 0, 0, 0);
      end = now;
      break;
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

function updateTimeRangeDisplay(timeRange) {
  const timeRangeEl = document.getElementById('timeRangeInfo');
  if (!timeRangeEl) return;

  const { start, end } = parseTimeRangeClient(timeRange);
  const startStr = formatTimestamp(start);
  const endStr = formatTimestamp(end);
  const label = timeRangeLabels[timeRange] || timeRange;
  
  timeRangeEl.innerHTML = `<span class="time-range-label">${label}</span> <span class="time-range-separator">|</span> <span class="time-range-value">${startStr} ~ ${endStr}</span>`;
}

// ========== 更新图表 ==========

function updateTimelineChart(points) {
  if (!timelineChart || !points.length) return;

  const dates = points.map(p => p.date);
  const counts = points.map(p => p.count);
  const groupCounts = points.map(p => p.group_count);
  const privateCounts = points.map(p => p.private_count);

  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' }
    },
    legend: {
      data: ['总消息', '群聊', '私聊']
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { rotate: 45 }
    },
    yAxis: {
      type: 'value'
    },
    series: [
      {
        name: '总消息',
        type: 'line',
        data: counts,
        smooth: true,
        areaStyle: { opacity: 0.3 }
      },
      {
        name: '群聊',
        type: 'line',
        data: groupCounts,
        smooth: true
      },
      {
        name: '私聊',
        type: 'line',
        data: privateCounts,
        smooth: true
      }
    ]
  };

  timelineChart.setOption(option);
}

function updatePlatformChart(platformStats) {
  if (!platformChart || !platformStats) return;

  const data = Object.entries(platformStats).map(([name, value]) => ({
    name: getPlatformIcon(name),
    value
  }));

  const option = {
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c} ({d}%)'
    },
    legend: {
      orient: 'vertical',
      right: '5%',
      top: 'center'
    },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['40%', '50%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 10,
          borderColor: '#fff',
          borderWidth: 2
        },
        label: {
          show: false,
          position: 'center'
        },
        emphasis: {
          label: {
            show: true,
            fontSize: 20,
            fontWeight: 'bold'
          }
        },
        labelLine: {
          show: false
        },
        data
      }
    ]
  };

  platformChart.setOption(option);
}

function updateSenderChart(senders) {
  if (!senderChart || !senders.length) return;

  const names = senders.map(s => truncate(s.sender_name || s.sender_id, 15));
  const counts = senders.map(s => s.count);

  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' }
    },
    grid: {
      left: '3%',
      right: '10%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'value'
    },
    yAxis: {
      type: 'category',
      data: names.reverse(),
      axisLabel: { width: 100, overflow: 'truncate' }
    },
    series: [
      {
        type: 'bar',
        data: counts.reverse(),
        itemStyle: {
          color: '#3498db',
          borderRadius: [0, 4, 4, 0]
        }
      }
    ]
  };

  senderChart.setOption(option);
}

function updateGroupChart(groups) {
  if (!groupChart || !groups.length) return;

  const ids = groups.map(g => truncate(g.group_id, 20));
  const counts = groups.map(g => g.count);

  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' }
    },
    grid: {
      left: '3%',
      right: '10%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'value'
    },
    yAxis: {
      type: 'category',
      data: ids.reverse(),
      axisLabel: { width: 100, overflow: 'truncate' }
    },
    series: [
      {
        type: 'bar',
        data: counts.reverse(),
        itemStyle: {
          color: '#27ae60',
          borderRadius: [0, 4, 4, 0]
        }
      }
    ]
  };

  groupChart.setOption(option);
}

// ========== 时间选择器 ==========

function bindTimeSelectorEvents() {
  const buttons = document.querySelectorAll('.time-btn');
  buttons.forEach(btn => {
    btn.addEventListener('click', async () => {
      // 更新选中状态
      buttons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      // 更新时间范围
      currentTimeRange = btn.dataset.range;
      if (currentTimeRange !== 'custom') {
        currentFilters = { time: currentTimeRange };
        // 更新时间范围显示
        updateTimeRangeDisplay(currentTimeRange);
        // 只重新加载排行数据，不影响时间趋势和平台分布
        await loadRankingData();
      }
    });
  });
}