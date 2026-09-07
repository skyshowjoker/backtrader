import {echarts, palette, colorCycle, compareColors} from '../constants.js';
import {formatNumber, roundNumber, formatAxisPercent} from './formatters.js';
import {toPairs, calcDrawdownPercent, navValuesToReturns, normalizedToReturns, collectChartDates, getChartWindow} from './helpers.js';

function zeroMarkLine() {
  return {
    silent: true,
    symbol: 'none',
    label: {show: false},
    lineStyle: {color: '#cfd8e4', width: 1, type: 'dashed'},
    data: [{yAxis: 0}],
  };
}

function buildReturnOption(result, toggles, compareSeries = [], chartRange = 'all') {
  const series = [];
  const axisColor = '#7a8798';
  const gridColor = '#e8edf4';
  const strategyReturnDates = result.strategy_return_dates?.length
    ? result.strategy_return_dates
    : result.nav_dates;
  const strategyReturnValues = result.strategy_return_values?.length
    ? result.strategy_return_values
    : navValuesToReturns(result.nav_values || []);

  function addReturnLine(key, dates, values, name, color, style = {}) {
    if (!toggles.includes(key) || !dates?.length || !values?.length) {
      return;
    }
    const item = {
      name,
      type: 'line',
      xAxisIndex: 0,
      yAxisIndex: 0,
      data: toPairs(dates, values),
      showSymbol: false,
      smooth: Boolean(style.smooth),
      sampling: 'lttb',
      connectNulls: true,
      z: style.z || 4,
      lineStyle: {
        width: style.width || 2,
        color,
        type: style.type || 'solid',
        opacity: style.opacity || 1,
      },
      itemStyle: {color},
      emphasis: {focus: 'series', lineStyle: {width: (style.width || 2) + 0.8}},
    };
    if (style.area) {
      item.areaStyle = {
        opacity: 0.16,
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          {offset: 0, color: style.areaColor || color},
          {offset: 1, color: 'rgba(255,255,255,0)'},
        ]),
      };
    }
    if (style.zeroLine) {
      item.markLine = zeroMarkLine();
    }
    series.push(item);
  }

  function addNavLine() {
    if (!toggles.includes('strategy_nav') || !result.nav_dates?.length || !result.nav_values?.length) {
      return;
    }
    series.push({
      name: '策略净值',
      type: 'line',
      xAxisIndex: 0,
      yAxisIndex: 1,
      data: toPairs(result.nav_dates, result.nav_values),
      showSymbol: false,
      sampling: 'lttb',
      connectNulls: true,
      z: 3,
      lineStyle: {width: 1.7, color: palette.green, type: 'dashed', opacity: 0.9},
      itemStyle: {color: palette.green},
      emphasis: {focus: 'series'},
    });
  }

  addReturnLine('strategy_return', strategyReturnDates, strategyReturnValues,
    '策略收益', palette.blue, {width: 3, area: true, areaColor: 'rgba(53, 100, 168, 0.24)', zeroLine: true, z: 8});
  addReturnLine('benchmark_return', result.benchmark_return_dates, result.benchmark_return_values,
    _benchmarkLabel(result), palette.slate, {type: 'dashed', width: 2.1, z: 5});
  addReturnLine('excess_return', result.excess_return_dates, result.excess_return_values,
    '超额收益', palette.gold, {width: 2, z: 6});
  addNavLine();

  for (const [index, item] of (result.underlying_series || []).entries()) {
    const color = colorCycle[index % colorCycle.length];
    addReturnLine('underlying_price', item.dates, normalizedToReturns(item.normalized),
      `${item.name} 价格收益`, color, {type: 'dotted', width: 1.5, opacity: 0.88});
    addReturnLine('underlying_return', item.dates, item.returns,
      `${item.name} 收益`, color, {type: 'dashed', width: 1.5, opacity: 0.88});
  }

  for (const [index, item] of (compareSeries || []).entries()) {
    const color = compareColors[index % compareColors.length];
    addReturnLine('compare_return', item.dates, item.returns,
      `${item.name || item.code} 对比收益`, color, {width: 1.9, opacity: 0.92});
  }

  if (toggles.includes('signals') && result.signals?.length) {
    const strategyReturnByDate = new Map((strategyReturnDates || []).map((date, index) => [date, strategyReturnValues?.[index]]));
    for (const type of ['buy', 'sell']) {
      const points = result.signals
        .filter((item) => item.type === type && strategyReturnByDate.has(item.date))
        .map((item) => [item.date, strategyReturnByDate.get(item.date), item.data_name || '', item.price, item.size]);
      if (points.length) {
        series.push({
          name: type === 'buy' ? '买入信号' : '卖出信号',
          type: 'scatter',
          xAxisIndex: 0,
          yAxisIndex: 0,
          data: points,
          symbol: 'triangle',
          symbolRotate: type === 'buy' ? 0 : 180,
          symbolSize: 12,
          symbolOffset: [0, type === 'buy' ? -9 : 9],
          z: 12,
          itemStyle: {color: type === 'buy' ? palette.green : palette.red, borderColor: '#fff', borderWidth: 1.5},
          tooltip: {
            formatter: (params) => `${params.seriesName}<br/>日期: ${params.value[0]}<br/>标的: ${params.value[2]}<br/>价格: ${formatNumber(params.value[3], 3)}<br/>数量: ${formatNumber(Math.abs(params.value[4] || 0), 0)}`,
          },
        });
      }
    }
  }

  const drawdown = calcDrawdownPercent(result.nav_values || []);
  if (result.nav_dates?.length && drawdown.length) {
    series.push({
      name: '策略回撤',
      type: 'line',
      xAxisIndex: 1,
      yAxisIndex: 2,
      data: toPairs(result.nav_dates, drawdown),
      showSymbol: false,
      sampling: 'lttb',
      connectNulls: true,
      lineStyle: {color: palette.red, width: 1.2},
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          {offset: 0, color: 'rgba(217, 89, 76, 0.30)'},
          {offset: 1, color: 'rgba(217, 89, 76, 0.04)'},
        ]),
      },
      itemStyle: {color: palette.red},
      markLine: zeroMarkLine(),
    });
  }

  const hasData = series.some((item) => item.data?.length);
  const hasNavAxis = toggles.includes('strategy_nav') && result.nav_values?.length;
  const chartWindow = getChartWindow(
    collectChartDates(result, compareSeries),
    chartRange,
  );

  return {
    color: Object.values(palette),
    animationDuration: 260,
    animationEasing: 'cubicOut',
    tooltip: {
      trigger: 'axis',
      axisPointer: {type: 'cross', link: [{xAxisIndex: [0, 1]}], label: {backgroundColor: '#25324a'}},
      borderWidth: 0,
      backgroundColor: 'rgba(16, 24, 40, 0.92)',
      textStyle: {color: '#fff', fontSize: 12},
      extraCssText: 'box-shadow:0 10px 28px rgba(16,24,40,.22);border-radius:6px;',
      formatter: _formatReturnTooltip,
    },
    legend: {
      type: 'scroll',
      top: 0,
      left: 4,
      right: 42,
      itemWidth: 18,
      itemHeight: 8,
      textStyle: {color: '#536071', fontWeight: 700},
    },
    toolbox: {
      right: 4,
      top: 0,
      itemSize: 14,
      feature: {
        restore: {title: '还原'},
        saveAsImage: {title: '保存'},
      },
    },
    grid: [
      {left: 62, right: hasNavAxis ? 70 : 34, top: 48, height: '62%', containLabel: false},
      {left: 62, right: hasNavAxis ? 70 : 34, top: '78%', height: '13%', containLabel: false},
    ],
    xAxis: [
      {
        type: 'time',
        gridIndex: 0,
        boundaryGap: false,
        axisLine: {lineStyle: {color: '#ccd6e3'}},
        axisTick: {show: false},
        axisLabel: {color: axisColor, hideOverlap: true},
        splitLine: {show: true, lineStyle: {color: gridColor}},
      },
      {
        type: 'time',
        gridIndex: 1,
        boundaryGap: false,
        axisLine: {lineStyle: {color: '#ccd6e3'}},
        axisTick: {show: false},
        axisLabel: {color: axisColor, hideOverlap: true},
        splitLine: {show: true, lineStyle: {color: gridColor}},
      },
    ],
    yAxis: [
      {
        type: 'value',
        gridIndex: 0,
        name: '累计收益',
        scale: true,
        axisLabel: {formatter: formatAxisPercent, color: axisColor},
        axisLine: {show: false},
        axisTick: {show: false},
        splitLine: {lineStyle: {color: gridColor}},
      },
      {
        type: 'value',
        gridIndex: 0,
        name: '净值',
        position: 'right',
        show: Boolean(hasNavAxis),
        scale: true,
        axisLabel: {formatter: (value) => formatNumber(value, 2), color: axisColor},
        axisLine: {show: false},
        axisTick: {show: false},
        splitLine: {show: false},
      },
      {
        type: 'value',
        gridIndex: 1,
        name: '回撤',
        max: 0,
        axisLabel: {formatter: formatAxisPercent, color: axisColor},
        axisLine: {show: false},
        axisTick: {show: false},
        splitLine: {lineStyle: {color: gridColor}},
      },
    ],
    axisPointer: {link: [{xAxisIndex: [0, 1]}]},
    dataZoom: [
      {type: 'inside', xAxisIndex: [0, 1], filterMode: 'none', ...chartWindow},
      {
        type: 'slider',
        xAxisIndex: [0, 1],
        height: 20,
        bottom: 4,
        borderColor: '#d7dee9',
        fillerColor: 'rgba(53, 100, 168, 0.14)',
        handleStyle: {color: '#3564a8'},
        textStyle: {color: axisColor},
        filterMode: 'none',
        ...chartWindow,
      },
    ],
    series,
    graphic: hasData ? [] : [{
      type: 'text',
      left: 'center',
      top: '42%',
      style: {text: '暂无回测数据，运行后将实时加载标准收益图', fill: '#98a3b3', fontSize: 15, fontWeight: 600},
    }],
  };
}

function buildSignalOption(analysis) {
  const timeline = analysis.timeline || [];
  const dates = timeline.map((item) => item.date);
  const hasData = dates.length > 0;

  return {
    animationDuration: 260,
    tooltip: {trigger: 'axis'},
    legend: {top: 0, right: 8, textStyle: {color: '#536071'}},
    grid: {left: 54, right: 50, top: 42, bottom: 36},
    xAxis: {type: 'category', data: dates, splitLine: {show: true, lineStyle: {color: '#edf1f6'}}},
    yAxis: [
      {type: 'value', name: '信号次数', splitLine: {lineStyle: {color: '#edf1f6'}}},
      {type: 'value', name: '净信号', splitLine: {show: false}},
    ],
    series: [
      {name: '买入信号', type: 'bar', data: timeline.map((item) => item.buy), itemStyle: {color: palette.green}},
      {name: '卖出信号', type: 'bar', data: timeline.map((item) => -item.sell), itemStyle: {color: palette.red}},
      {name: '净信号累积', type: 'line', yAxisIndex: 1, data: timeline.map((item) => item.exposure), itemStyle: {color: palette.gold}, lineStyle: {width: 2}},
    ],
    graphic: hasData ? [] : [{
      type: 'text',
      left: 'center',
      top: 'middle',
      style: {text: '暂无信号数据', fill: '#98a3b3', fontSize: 14, fontWeight: 600},
    }],
  };
}

function buildDrawdownOption(result) {
  const dates = result.nav_dates || [];
  const drawdown = calcDrawdownPercent(result.nav_values || []);

  return {
    animationDuration: 260,
    tooltip: {
      trigger: 'axis',
      axisPointer: {type: 'cross', label: {backgroundColor: '#25324a'}},
      borderWidth: 0,
      backgroundColor: 'rgba(16, 24, 40, 0.92)',
      textStyle: {color: '#fff', fontSize: 12},
      valueFormatter: (value) => `${formatNumber(value, 2)}%`,
    },
    grid: {left: 58, right: 26, top: 18, bottom: 36},
    xAxis: {
      type: 'time',
      boundaryGap: false,
      axisTick: {show: false},
      axisLabel: {color: '#7a8798'},
      splitLine: {show: true, lineStyle: {color: '#e8edf4'}},
    },
    yAxis: {
      type: 'value',
      name: '回撤',
      max: 0,
      axisTick: {show: false},
      axisLabel: {formatter: formatAxisPercent, color: '#7a8798'},
      splitLine: {lineStyle: {color: '#e8edf4'}},
    },
    series: [{
      name: '回撤',
      type: 'line',
      data: toPairs(dates, drawdown),
      showSymbol: false,
      sampling: 'lttb',
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          {offset: 0, color: 'rgba(217, 89, 76, 0.30)'},
          {offset: 1, color: 'rgba(217, 89, 76, 0.04)'},
        ]),
      },
      lineStyle: {color: palette.red, width: 1.6},
      itemStyle: {color: palette.red},
      markLine: zeroMarkLine(),
    }],
    graphic: dates.length ? [] : [{
      type: 'text',
      left: 'center',
      top: 'middle',
      style: {text: '暂无数据', fill: '#98a3b3', fontSize: 14, fontWeight: 600},
    }],
  };
}

function _benchmarkLabel(result) {
  const source = result.benchmark_source || '';
  if (source.startsWith('proxy:')) {
    return `基准收益 (${source.split(':')[1]}代用)`;
  }
  return '基准收益';
}

function _formatReturnTooltip(params = []) {
  const items = Array.isArray(params) ? params : [params];
  const visible = items.filter((item) => item && item.value && item.value[1] !== null && item.value[1] !== undefined);
  if (!visible.length) {
    return '';
  }

  const date = visible[0].axisValueLabel || visible[0].value?.[0] || '';
  const rows = visible.map((item) => {
    const value = Array.isArray(item.value) ? item.value[1] : item.value;
    if (item.seriesType === 'scatter') {
      return `<div>${item.marker}${item.seriesName}: ${item.value[2] || '--'} / ${formatNumber(item.value[3], 3)}</div>`;
    }
    const isNav = item.seriesName === '策略净值';
    const formatted = isNav ? formatNumber(value, 3) : `${formatNumber(value, Math.abs(Number(value)) >= 100 ? 1 : 2)}%`;
    return `<div>${item.marker}${item.seriesName}: <b>${formatted}</b></div>`;
  }).join('');

  return `<div class="chart-tooltip"><div class="chart-tooltip-date">${date}</div>${rows}</div>`;
}

export {buildReturnOption, buildSignalOption, buildDrawdownOption};
