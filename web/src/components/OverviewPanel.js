import {html, echarts, useEffect, useRef, useState} from '../constants.js';
import {curveOptions, chartRangeOptions, DEFAULT_TOGGLES} from '../constants.js';
import {toggleValue} from '../utils/helpers.js';
import {buildReturnOption} from '../utils/chartBuilders.js';

export default function OverviewPanel({result, compareSeries, chartRange, setChartRange}) {
  const chartRef = useRef(null);
  const instanceRef = useRef(null);
  const [toggles, setToggles] = useState(DEFAULT_TOGGLES);

  useEffect(() => {
    if (!chartRef.current) return;
    if (!instanceRef.current) {
      instanceRef.current = echarts.init(chartRef.current, null, {renderer: 'canvas'});
    }
    const option = buildReturnOption(result || {}, toggles, compareSeries || [], chartRange);
    instanceRef.current.setOption(option, true);
    instanceRef.current.resize();

    const onResize = () => instanceRef.current?.resize();
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [result, toggles, compareSeries, chartRange]);

  useEffect(() => () => instanceRef.current?.dispose(), []);

  return html`
    <div className="overview-panel">
      <div className="chart-controls">
        <div className="curve-toggles">
          ${curveOptions.map(([key, label]) => html`
            <button key=${key}
              className=${toggles.includes(key) ? 'toggle active' : 'toggle'}
              onClick=${() => setToggles((t) => toggleValue(t, key))}>
              ${label}
            </button>
          `)}
        </div>
        <div className="range-toggles">
          ${chartRangeOptions.map(([value, label]) => html`
            <button key=${value}
              className=${chartRange === value ? 'toggle active' : 'toggle'}
              onClick=${() => setChartRange(value)}>
              ${label}
            </button>
          `)}
        </div>
      </div>
      <div ref=${chartRef} className="chart-canvas"></div>
    </div>
  `;
}
