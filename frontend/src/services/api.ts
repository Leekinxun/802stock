import type {
  DashboardPayload,
  MarketSentimentResponse,
  MarketSnapshot,
  RealtimeQuoteResponse,
  SignalResponse,
  SignalSyncResponse,
  WencaiIntersectionJobCreateResponse,
  WencaiIntersectionJobResponse,
  WencaiIntersectionRequest,
  WencaiIntersectionResponse,
  WencaiQueryRequest,
  WencaiQueryResponse,
  WatchlistCreate,
  WatchlistItem,
  WatchlistResponse,
} from '../types'

const API_BASE = (import.meta.env.VITE_API_BASE_URL?.trim() || '/api/v1').replace(/\/$/, '')

const fallbackDashboard: DashboardPayload = {
  metrics: [
    { label: 'Legacy Python Modules', value: '--', hint: '等待后端启动', tone: 'info' },
    { label: 'Pending TODOs', value: '--', hint: '等待后端启动', tone: 'warning' },
    { label: 'Reusable Collectors', value: '--', hint: '等待后端启动', tone: 'success' },
    { label: 'Frontend Status', value: 'local preview', hint: '前端可先独立开发样式', tone: 'accent' },
  ],
  hot_sectors: [
    { name: '事件驱动精选', change_pct: '+0.0%', leader: '待接数据', thesis: '后端未启动时展示占位卡片' },
  ],
  event_stream: [
    { title: '等待后端 API', source: 'frontend-fallback', timestamp: '--', sentiment: 'neutral', summary: '启动 FastAPI 后将加载真实 dashboard 数据。' },
  ],
  strategy_workbench: [
    { name: 'Signal Engine', status: 'pending', note: '待接入真实市场事件和板块异动' },
  ],
  migration: {
    completed: ['React workbench 已创建'],
    next_up: ['等待后端接口联通'],
    blockers: ['本地后端尚未启动'],
  },
  platform_status: {
    legacy_root: 'pending backend',
    module_counts: {},
    todo_count: 0,
    implemented_collectors: [],
    critical_findings: ['等待后端状态接口'],
  },
}

export async function fetchDashboard(): Promise<DashboardPayload> {
  try {
    const response = await fetch(`${API_BASE}/dashboard`)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    return (await response.json()) as DashboardPayload
  } catch (error) {
    console.warn('dashboard api unavailable, using fallback', error)
    return fallbackDashboard
  }
}

const fallbackMarketSnapshot: MarketSnapshot = {
  hot_sectors: fallbackDashboard.hot_sectors,
  anomalies: [
    {
      title: '等待市场异动接口',
      anomaly_type: 'pending',
      summary: '后端未启动时展示占位数据。',
      timestamp: '--',
      source: 'frontend-fallback',
      stock_code: null,
      stock_name: null,
    },
  ],
  longhubang: [
    {
      stock_code: '--',
      stock_name: '等待龙虎榜接口',
      reason: 'pending',
      net_amount: '--',
      buy_total: '--',
      sell_total: '--',
      timestamp: '--',
      source: 'frontend-fallback',
    },
  ],
}

export async function fetchMarketSnapshot(): Promise<MarketSnapshot> {
  try {
    const response = await fetch(`${API_BASE}/market/snapshot`)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    return (await response.json()) as MarketSnapshot
  } catch (error) {
    console.warn('market snapshot api unavailable, using fallback', error)
    return fallbackMarketSnapshot
  }
}

const fallbackMarketSentiment: MarketSentimentResponse = {
  points: [],
  supported: false,
  source: 'frontend-fallback',
  latest_trade_date: null,
  note: '当前后端未返回情绪踩点数据。',
}

export async function fetchMarketSentiment(): Promise<MarketSentimentResponse> {
  try {
    const response = await fetch(`${API_BASE}/market/sentiment?limit=5`)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    return (await response.json()) as MarketSentimentResponse
  } catch (error) {
    console.warn('market sentiment api unavailable, using fallback', error)
    return fallbackMarketSentiment
  }
}

export async function fetchWatchlist(): Promise<WatchlistResponse> {
  try {
    const response = await fetch(`${API_BASE}/watchlist`)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    return (await response.json()) as WatchlistResponse
  } catch (error) {
    console.warn('watchlist api unavailable, using fallback', error)
    return { items: [] }
  }
}

export async function createWatchlistItem(payload: WatchlistCreate): Promise<WatchlistItem> {
  const response = await fetch(`${API_BASE}/watchlist`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    throw new Error(`Failed to create watchlist item: HTTP ${response.status}`)
  }

  return (await response.json()) as WatchlistItem
}

export async function deleteWatchlistItem(itemId: number): Promise<void> {
  const response = await fetch(`${API_BASE}/watchlist/${itemId}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    throw new Error(`Failed to delete watchlist item: HTTP ${response.status}`)
  }
}

export async function fetchSignals(): Promise<SignalResponse> {
  try {
    const response = await fetch(`${API_BASE}/signals?limit=20`)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    return (await response.json()) as SignalResponse
  } catch (error) {
    console.warn('signals api unavailable, using fallback', error)
    return { items: [] }
  }
}

export async function syncSignals(): Promise<SignalSyncResponse> {
  const response = await fetch(`${API_BASE}/signals/sync`, {
    method: 'POST',
  })

  if (!response.ok) {
    throw new Error(`Failed to sync signals: HTTP ${response.status}`)
  }

  return (await response.json()) as SignalSyncResponse
}

export async function fetchRealtimeQuote(symbol: string): Promise<RealtimeQuoteResponse> {
  try {
    const response = await fetch(`${API_BASE}/market/realtime/${encodeURIComponent(symbol)}`)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    return (await response.json()) as RealtimeQuoteResponse
  } catch (error) {
    console.warn('realtime quote api unavailable, using fallback', error)
    return {
      symbol,
      market_symbol: symbol,
      source: 'frontend-fallback',
      supported: false,
      note: '当前后端未返回腾讯实时快照。',
    }
  }
}

export async function runWencaiQuery(payload: WencaiQueryRequest): Promise<WencaiQueryResponse> {
  try {
    const response = await fetch(`${API_BASE}/market/wencai-query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    return (await response.json()) as WencaiQueryResponse
  } catch (error) {
    console.warn('wencai query api unavailable, using fallback', error)
    return {
      query: payload.query,
      sort_key: payload.sort_key ?? null,
      sort_order: payload.sort_order ?? null,
      query_type: payload.query_type,
      source: 'frontend-fallback',
      supported: false,
      columns: [],
      items: [],
      note: '当前后端未返回问财结果，请检查 WENCAI_COOKIE、pywencai 或后端服务状态。',
    }
  }
}

export async function runWencaiIntersection(payload: WencaiIntersectionRequest): Promise<WencaiIntersectionResponse> {
  try {
    const response = await fetch(`${API_BASE}/market/wencai-intersection`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    return (await response.json()) as WencaiIntersectionResponse
  } catch (error) {
    console.warn('wencai intersection api unavailable, using fallback', error)
    return {
      query: payload.queries.join(' ∩ '),
      sort_key: payload.sort_key ?? null,
      sort_order: payload.sort_order ?? null,
      query_type: payload.query_type,
      source: 'frontend-fallback',
      supported: false,
      columns: [],
      items: [],
      requested_query_count: payload.queries.length,
      executed_query_count: 0,
      intersection_count: 0,
      watchlist_added_count: 0,
      watchlist_existing_count: 0,
      step_results: [],
      note: '当前后端未返回问财交集结果，请检查 WENCAI_COOKIE、pywencai 或后端服务状态。',
    }
  }
}

export async function createWencaiIntersectionJob(payload: WencaiIntersectionRequest): Promise<WencaiIntersectionJobCreateResponse> {
  const response = await fetch(`${API_BASE}/market/wencai-intersection/jobs`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    throw new Error(`Failed to create wencai intersection job: HTTP ${response.status}`)
  }

  return (await response.json()) as WencaiIntersectionJobCreateResponse
}

export async function fetchWencaiIntersectionJob(jobId: string): Promise<WencaiIntersectionJobResponse> {
  const response = await fetch(`${API_BASE}/market/wencai-intersection/jobs/${encodeURIComponent(jobId)}`)

  if (!response.ok) {
    throw new Error(`Failed to fetch wencai intersection job: HTTP ${response.status}`)
  }

  return (await response.json()) as WencaiIntersectionJobResponse
}
