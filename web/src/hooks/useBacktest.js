import {html, useEffect, useState, useRef, API_BASE} from '../constants.js';
import {fetchJson, validateRunConfig, mergeBacktestResult} from '../utils/helpers.js';

const api = (path) => `${API_BASE}${path}`;

export default function useBacktest() {
  const [taskId, setTaskId] = useState('');
  const [result, setResult] = useState({});
  const [runStatus, setRunStatus] = useState({type: 'idle', text: '就绪'});
  const [runProgress, setRunProgress] = useState({stage: 'idle'});
  const [runStartedAt, setRunStartedAt] = useState(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [taskHistory, setTaskHistory] = useState([]);
  const [activityLog, setActivityLog] = useState(['系统就绪']);
  const timerRef = useRef(null);

  const appendLog = (msg) => {
    const time = new Date().toLocaleTimeString('zh-CN', {hour12: false});
    setActivityLog((prev) => [`${time}  ${msg}`, ...prev].slice(0, 80));
  };

  // Polling effect
  useEffect(() => {
    if (!taskId) return;
    let stopped = false;
    async function poll() {
      try {
        const r = await fetchJson(api(`/backtests/${taskId}`));
        if (stopped) return;
        setRunProgress(r.progress || r.data?.progress || {});
        if (r.data) setResult((prev) => mergeBacktestResult(prev, r.data));
        if (r.status === 'done') {
          setRunStatus({type: 'success', text: '回测完成'});
          setRunStartedAt(null); setTaskId('');
        } else if (r.status === 'error') {
          setRunStatus({type: 'error', text: r.data || '回测失败'});
          setRunStartedAt(null); setTaskId('');
        } else {
          setTimeout(poll, 900);
        }
      } catch { if (!stopped) setTimeout(poll, 1500); }
    }
    poll();
    return () => { stopped = true; };
  }, [taskId]);

  // Timer effect
  useEffect(() => {
    if (!taskId || !runStartedAt) return;
    timerRef.current = setInterval(() => setElapsedSeconds((Date.now() - runStartedAt) / 1000), 250);
    return () => clearInterval(timerRef.current);
  }, [taskId, runStartedAt]);

  const runBacktest = async (strategy, params, config) => {
    const err = validateRunConfig(config);
    if (err) { setRunStatus({type: 'error', text: err}); return; }
    setRunStatus({type: 'running', text: '启动中'});
    setResult({}); setRunProgress({stage: 'queued'}); setElapsedSeconds(0); setRunStartedAt(Date.now());
    try {
      const r = await fetchJson(api('/backtests'), {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({strategy, params, ...config}),
      });
      setTaskId(r.task_id);
    } catch (e) { setRunStatus({type: 'error', text: e.message}); setRunStartedAt(null); }
  };

  const refreshTasks = async () => {
    try { setTaskHistory((await fetchJson(api('/backtests'))).tasks || []); } catch {}
  };

  const openTask = async (id) => {
    try {
      const r = await fetchJson(api(`/backtests/${id}`));
      if (r.data) setResult(r.data);
      setRunStatus({type: 'success', text: `已载入 ${id}`});
    } catch {}
  };

  return { taskId, result, runStatus, runProgress, elapsedSeconds, taskHistory, activityLog,
           setRunStatus, runBacktest, refreshTasks, openTask, appendLog, isRunning: !!taskId };
}
