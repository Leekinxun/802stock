# STOCK Quant Workbench

当前仓库已清理为**最小可运行量化工作台**，只保留真正接入并验证过的部分：

- **FastAPI 后端**：实时事件、热点板块、市场异动、龙虎榜、watchlist、signal 同步
- **React 前端**：市场首页、观察池/实时信号、问财自然语言筛选、TODO 子界面
- **少量 legacy adapter**：已收拢到 `backend/app/legacy/`，继续给新平台供数

当前版本已经把**问财交集筛选**升级为单机可部署的**生产基线版本**：

- 前端支持动态增减问财条件框
- 后端支持多条件串行执行 + 股票代码交集
- 问财长任务已改为**后台 Job + 轮询状态**
- 任务状态、步骤结果、最终结果持久化到 SQLite
- 服务重启后会自动尝试恢复 `pending / running` 的问财任务

已删除：

- 旧 Flask API
- 未接入的分析/决策/知识图谱/调度脚手架
- 失效或未落地的旧测试、脚本、文档和依赖清单

## 当前目录

```text
STOCK/
├── backend/               # Python 单项目：FastAPI + legacy adapters + tests
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── legacy/        # legacy collectors / datasources / models / utils
│   │   ├── schemas/
│   │   └── services/
│   ├── tests/
│   └── requirements.txt
├── frontend/              # React + Vite 可视化工作台
├── .env.example
└── .gitignore
```

## 后端能力

### 市场接口
- `GET /api/v1/health`
- `GET /api/v1/dashboard`
- `GET /api/v1/events`
- `GET /api/v1/market/hot-sectors`
- `GET /api/v1/market/anomalies`
- `GET /api/v1/market/longhubang`
- `GET /api/v1/market/intraday/{symbol}`
- `GET /api/v1/market/realtime/{symbol}`
- `GET /api/v1/market/delisted-stocks`
- `POST /api/v1/market/wencai-query`
- `POST /api/v1/market/wencai-intersection`
- `POST /api/v1/market/wencai-intersection/jobs`
- `GET /api/v1/market/wencai-intersection/jobs/{job_id}`
- `GET /api/v1/market/sector-stocks/{sector_code}`
- `GET /api/v1/market/snapshot`

### 观察池 / Signal
- `GET /api/v1/watchlist`
- `POST /api/v1/watchlist`
- `DELETE /api/v1/watchlist/{id}`
- `GET /api/v1/signals`
- `POST /api/v1/signals/sync`

## 快速开始

### 1. 后端

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

### 3. 环境变量

```bash
cp .env.example .env
```

后端启动时会自动读取项目根目录 `.env`。

如果你已经在本机 Chrome 登录了问财，也可以直接执行：

```bash
.venv/bin/python scripts/update_wencai_cookie.py
```

脚本会自动提取问财相关 Cookie，并写回项目根目录 `.env` 的 `WENCAI_COOKIE`。

可选配置：

- `CODENAME_CSV_PATH`：可选；不传时默认尝试读取仓库根目录的 `codename.csv`
- `WENCAI_COOKIE`：可选；用于 `pywencai` 查询。若未配置或失效，后端会尝试自动读取本机 Chrome 登录态

股票代码格式现在会自动转换，以下格式都可直接使用：

- `000001.SH`
- `SH000001`
- `000001`

## 观察池实时数据来源

- **优先来源**：腾讯 `qt.gtimg.cn` 实时快照 / 盘口数据
- **市场级来源**：同花顺网页抓取（热点板块 / 市场异动 / 龙虎榜 / 事件流）
- **当前取舍**：当日分钟线接口暂未启用
- **补充能力**：可通过 `pywencai` 查询退市股票列表

问财自然语言条件句也支持走后端转发，例如：

```json
POST /api/v1/market/wencai-query
{
  "query": "沪深主板且非ST且价格小于23且近10年涨停总数大于16，昨日首板涨停且11:30前涨停，竞价涨跌幅>3%<9%",
  "sort_key": "涨停次数",
  "sort_order": "desc",
  "limit": 20,
  "query_type": "stock"
}
```

更推荐的生产方式是直接创建后台 Job：

```json
POST /api/v1/market/wencai-intersection/jobs
{
  "queries": [
    "沪深主板且非ST且价格小于23",
    "近10年涨停总数大于16，昨日首板涨停且11:30前涨停",
    "竞价涨跌幅>3%<9%"
  ],
  "sort_key": "涨停次数",
  "sort_order": "desc",
  "limit": 20,
  "query_type": "stock",
  "interval_seconds": 90,
  "import_to_watchlist": true
}
```

拿到 `job_id` 后轮询：

```text
GET /api/v1/market/wencai-intersection/jobs/{job_id}
```

任务完成后，后端会自动：

1. 串行执行所有问财语句
2. 按股票代码求交集
3. 自动导入观察池（去重）
4. 返回每一步的执行情况与最终交集结果

前端问财结果表当前会聚焦展示以下字段（若结果中存在）：

- 股票代码
- 股票简称
- 收盘价
- 当日涨停价
- 9.95%价格
- 开盘价
- 最高价
- 最低价

也就是说，观察池页面现在会优先显示腾讯实时行情的：

- 当前价
- 涨跌 / 涨跌幅
- 买一 / 卖一
- 成交量 / 成交额
- 买卖盘大单 / 小单

如果腾讯实时快照不可用，当前不会再回退到 StockAPI，而是直接提示实时行情暂不可用。

## 本地持久化

当前 watchlist / market snapshot / signals 默认保存在：

```text
backend/.runtime/quant_platform.db
```

问财后台任务也持久化在同一个 SQLite 中。

可通过环境变量覆盖：

- `QUANT_RUNTIME_DIR`
- `QUANT_SQLITE_PATH`

## 验证

### 后端回归测试

```bash
.venv/bin/python -m unittest backend.tests.test_api_regression -v
```

如果要启用 `pywencai`：

1. 安装 `backend/requirements.txt` 中新增的 `pywencai`
2. 建议同时安装并保留 `browser-cookie3`（已写入 requirements），用于自动读取本机 Chrome Cookie
3. 可选：在 `.env` 里手动配置 `WENCAI_COOKIE`
4. 如不手动配置 Cookie，确保本机 Chrome 已登录问财，且终端具备读取浏览器 Cookie 的权限
5. 确保本机 Node.js 环境可用（`pywencai` 依赖 Node.js）

### 前端构建

```bash
cd frontend
npm run build
```

## 当前边界

- signal 还是**规则评分版**
- 仍依赖腾讯 / 同花顺源站稳定性
- 当前问财任务还是**单机进程内线程池**模型，不是分布式任务系统
- 还没有 PostgreSQL repository / portfolio / risk / backtest

## 下一步优化建议

### P0：部署与运行稳定性

1. Docker / docker-compose 打包
2. Nginx 反向代理
3. systemd / supervisor 启动配置
4. 结构化日志、错误告警与访问日志
5. `/health` 扩展为数据库 / 线程池 / 外部源站检查

### P1：问财任务进一步生产化

1. 将问财 Job 从**进程内线程池**升级为 Redis + Celery / RQ
2. 增加任务取消、任务超时、任务历史列表
3. 加入并发上限、频控、重试和缓存
4. 为任务结果增加过期清理与归档策略

### P2：数据层升级

1. PostgreSQL repository
2. watchlist / signals / wencai_jobs 从 SQLite 平滑迁移到 PostgreSQL
3. 增加快照归档与索引优化

### P3：策略与交易工作台

1. signal explain / factor breakdown
2. portfolio / positions / risk exposure
3. 自选池分组、主题观察池、策略备注联动
4. 回测 / 复盘 / 交易日志工作台

### P4：安全与权限

1. 登录鉴权
2. 操作审计日志
3. API token / 角色权限控制
4. 敏感环境变量隔离与部署模板
