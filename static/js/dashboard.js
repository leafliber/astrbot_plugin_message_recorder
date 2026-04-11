/**
 * 仪表盘页面逻辑
 */

// ECharts 图表实例
let timelineChart = null;
let platformChart = null;
let senderChart = null;
let groupChart = null;

// 当前时间范围
let currentTimeRange = 'last7d';
let currentFilters = {};

// ========== 初始化 ==========

document.addEventListener('DOMContentLoaded', async () => {
  // 初始化图表
  initCharts();

  // 加载统计数据
  await loadDashboardData();

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

  // 加载时间趋势
  const timelineResult = await api.getTimeline('day', currentFilters);
  if (timelineResult.success) {
    updateTimelineChart(timelineResult.data.points);
  }

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

  hideLoading();
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

  // 更新时间范围显示
  const timeRangeEl = document.getElementById('timeRangeInfo');
  if (timeRangeEl && stats.time_range) {
    if (stats.time_range.start && stats.time_range.end) {
      timeRangeEl.textContent = `${stats.time_range.start} ~ ${stats.time_range.end}`;
    }
  }
}

function formatNumber(num) {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M';
  } else if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K';
  }
  return num.toString();
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
        await loadDashboardData();
      }
    });
  });
}