import {html, echarts, useEffect, useRef} from '../constants.js';
import {buildDrawdownOption} from '../utils/chartBuilders.js';

export default function DrawdownChart({result}) {
  const ref = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!ref.current) return;
    chartRef.current = echarts.init(ref.current, null, {renderer: 'canvas'});
    const onResize = () => chartRef.current?.resize();
    window.addEventListener('resize', onResize);
    return () => { window.removeEventListener('resize', onResize); chartRef.current?.dispose(); };
  }, []);

  useEffect(() => {
    if (!chartRef.current) return;
    chartRef.current.setOption(buildDrawdownOption(result || {}), true);
  }, [result]);

  return html`<div ref=${ref} className="drawdown-chart"></div>`;
}
