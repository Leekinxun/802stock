# STOCK FastAPI Backend

当前后端已不是“骨架”，而是最小可运行服务，包含：

- Dashboard / Events / Market Snapshot API
- Watchlist CRUD
- Signal 同步与规则评分
- 腾讯实时快照 / 盘口优先行情
- pywencai 退市股票查询接口
- SQLite 本地持久化
- 回归测试

## 启动

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

后端会自动读取项目根目录的 `.env`。

## 股票代码兼容

后端已兼容以下股票代码输入：

- `000001.SH`
- `SH000001`
- `000001`

分时、实时行情、信号匹配会自动转换到对应数据源需要的格式。
如果仓库根目录存在 `codename.csv`，服务会优先用它辅助识别交易所归属；也可通过 `CODENAME_CSV_PATH` 显式指定路径。

## 当前数据来源

- 腾讯 `qt.gtimg.cn`：单股实时快照 / 盘口
- 同花顺网页源：热点板块 / 市场异动 / 龙虎榜 / 事件流
- pywencai：退市股票查询
- 当日分钟线：当前版本暂未启用

## pywencai 配置

在项目根目录 `.env` 中可选配置：

```bash
WENCAI_COOKIE=your_browser_cookie_here
```

如果你已经在本机 Chrome 登录了问财，可直接运行：

```bash
.venv/bin/python scripts/update_wencai_cookie.py
```

脚本会自动读取问财相关 Cookie，并写回项目根目录 `.env`。

对应接口：

- `GET /api/v1/market/delisted-stocks`
- `POST /api/v1/market/wencai-query`

说明：

- `pywencai` 支持优先读取 `.env` 中的 `WENCAI_COOKIE`
- 若 `.env` 缺失或 Cookie 失效，后端会尝试自动读取本机 Chrome 登录态（依赖 `browser-cookie3`）
- 运行环境需具备 Node.js（`pywencai` 的运行要求）

自然语言条件句可以直接透传给 `pywencai`，例如：

```json
{
  "query": "沪深主板且非ST且价格小于23且近10年涨停总数大于16，昨日首板涨停且11:30前涨停，竞价涨跌幅>3%<9%",
  "sort_key": "涨停次数",
  "sort_order": "desc",
  "limit": 20,
  "query_type": "stock"
}
```

前端问财表格当前只保留这些核心列（命中时展示）：

- 股票代码
- 股票简称
- 收盘价
- 当日涨停价
- 9.95%价格
- 开盘价
- 最高价
- 最低价

## 主要目录

```text
backend/
├── app/api/routes/        # 路由
├── app/services/          # dashboard / live data / signal / store
├── app/schemas/           # Pydantic schema
├── app/core/              # 配置
├── app/legacy/            # 收拢后的 legacy collectors / datasources / models / utils
└── tests/                 # unittest 回归测试
```
