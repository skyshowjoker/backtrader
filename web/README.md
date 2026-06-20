# BackQuant React UI

前端和后端分离：

- 前端：`web/`，React + ECharts，独立静态服务，默认端口 `5173`
- 后端：`ui/api.py`，Flask JSON API，默认端口 `8060`

启动：

```bash
venv/bin/python -m ui.api
/Users/mac/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node web/server.mjs
```

访问：

```text
http://127.0.0.1:5173
```
