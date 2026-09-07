const React = window.React;
const ReactDOM = window.ReactDOM;
const htm = window.htm;
const echarts = window.echarts;

if (!React || !ReactDOM || !htm || !echarts) {
  throw new Error('前端依赖未加载，请确认 /vendor 下的 React、HTM、ECharts 文件可访问。');
}

const {useEffect, useMemo, useRef, useState, useCallback} = React;
const {createRoot} = ReactDOM;
const html = htm.bind(React.createElement);
const API_BASE = window.__BACKTRADER_API__ || 'http://127.0.0.1:8060/api';

const DEFAULT_TOGGLES = [
  'strategy_return',
  'benchmark_return',
  'excess_return',
  'compare_return',
  'signals',
];

const curveOptions = [
  ['strategy_nav', '策略净值'],
  ['strategy_return', '策略收益'],
  ['benchmark_return', '基准收益'],
  ['excess_return', '超额收益'],
  ['compare_return', '对比标的'],
  ['underlying_price', '标的价格'],
  ['underlying_return', '标的收益'],
  ['signals', '买卖信号'],
];

const chartRangeOptions = [
  ['1m', '1月'],
  ['3m', '3月'],
  ['6m', '6月'],
  ['ytd', 'YTD'],
  ['all', '全部'],
];

const palette = {
  blue: '#3564a8',
  green: '#16a085',
  gold: '#d59b43',
  red: '#d9594c',
  slate: '#6d7d93',
  violet: '#7764c8',
  cyan: '#2596a6',
};

const colorCycle = [palette.violet, palette.cyan, '#8c6d4f', '#536f9f', '#b85b4b'];
const compareColors = ['#0f766e', '#b7791f', '#7c3aed', '#be123c', '#2563eb', '#5f6f83'];

export {
  React, ReactDOM, htm, echarts, html,
  useEffect, useMemo, useRef, useState, useCallback, createRoot,
  API_BASE, DEFAULT_TOGGLES, curveOptions, chartRangeOptions, palette,
  colorCycle, compareColors,
};
