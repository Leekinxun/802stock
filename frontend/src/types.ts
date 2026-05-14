export type MetricCard = {
  label: string
  value: string
  hint: string
  tone: string
}

export type HotSectorItem = {
  name: string
  change_pct: string
  leader: string
  thesis: string
  code?: string | null
  source?: string | null
}

export type EventFeedItem = {
  title: string
  source: string
  timestamp: string
  sentiment: string
  summary: string
}

export type StrategyWorkbenchItem = {
  name: string
  status: string
  note: string
}

export type MigrationStatus = {
  completed: string[]
  next_up: string[]
  blockers: string[]
}

export type PlatformStatus = {
  legacy_root: string
  module_counts: Record<string, number>
  todo_count: number
  implemented_collectors: string[]
  critical_findings: string[]
}

export type DashboardPayload = {
  metrics: MetricCard[]
  hot_sectors: HotSectorItem[]
  event_stream: EventFeedItem[]
  strategy_workbench: StrategyWorkbenchItem[]
  migration: MigrationStatus
  platform_status: PlatformStatus
}

export type MarketAnomalyItem = {
  title: string
  stock_code?: string | null
  stock_name?: string | null
  anomaly_type: string
  summary: string
  timestamp: string
  source: string
}

export type LonghubangItem = {
  stock_code: string
  stock_name: string
  reason: string
  net_amount: string
  buy_total: string
  sell_total: string
  timestamp: string
  source: string
}

export type MarketSnapshot = {
  hot_sectors: HotSectorItem[]
  anomalies: MarketAnomalyItem[]
  longhubang: LonghubangItem[]
}

export type MarketSentimentPoint = {
  trade_date: string
  rise_count: number
  total_count: number
  ratio: number
  source: string
  note?: string | null
}

export type MarketSentimentResponse = {
  points: MarketSentimentPoint[]
  supported: boolean
  source: string
  latest_trade_date?: string | null
  note?: string | null
}

export type SectorStockItem = {
  code: string
  name: string
  exchange: string
  sector: string
  concepts: string[]
  source: string
}

export type SectorStockResponse = {
  sector_code: string
  items: SectorStockItem[]
}

export type IntradayTrendPoint = {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume?: number | null
  amount?: number | null
}

export type IntradayTrendResponse = {
  symbol: string
  source: string
  supported: boolean
  points: IntradayTrendPoint[]
  open_price?: number | null
  latest_price?: number | null
  day_high?: number | null
  day_low?: number | null
  change_pct?: number | null
  note?: string | null
}

export type RealtimeOrderFlow = {
  buy_large?: number | null
  buy_small?: number | null
  sell_large?: number | null
  sell_small?: number | null
}

export type RealtimeQuoteResponse = {
  symbol: string
  market_symbol: string
  source: string
  supported: boolean
  name?: string | null
  price?: number | null
  prev_close?: number | null
  open_price?: number | null
  high_price?: number | null
  low_price?: number | null
  change?: number | null
  change_pct?: number | null
  volume_hands?: number | null
  amount_wan?: number | null
  quote_time?: string | null
  bid_price_1?: number | null
  bid_volume_1?: number | null
  ask_price_1?: number | null
  ask_volume_1?: number | null
  order_flow?: RealtimeOrderFlow | null
  note?: string | null
}

export type WencaiQueryRequest = {
  query: string
  sort_key?: string | null
  sort_order?: string | null
  limit: number
  query_type: string
}

export type WencaiQueryResponse = {
  query: string
  sort_key?: string | null
  sort_order?: string | null
  query_type: string
  source: string
  supported: boolean
  columns: string[]
  items: Array<Record<string, unknown>>
  note?: string | null
}

export type WencaiIntersectionStepResult = {
  query: string
  supported: boolean
  item_count: number
  note?: string | null
}

export type WencaiIntersectionRequest = {
  queries: string[]
  sort_key?: string | null
  sort_order?: string | null
  limit: number
  query_type: string
  interval_seconds: number
  import_to_watchlist: boolean
}

export type WencaiIntersectionResponse = {
  query: string
  sort_key?: string | null
  sort_order?: string | null
  query_type: string
  source: string
  supported: boolean
  columns: string[]
  items: Array<Record<string, unknown>>
  requested_query_count: number
  executed_query_count: number
  intersection_count: number
  watchlist_added_count: number
  watchlist_existing_count: number
  step_results: WencaiIntersectionStepResult[]
  note?: string | null
}

export type WencaiIntersectionJobCreateResponse = {
  job_id: string
  status: string
  created_at: string
  requested_query_count: number
  poll_after_seconds: number
  note?: string | null
}

export type WencaiIntersectionJobResponse = {
  job_id: string
  status: string
  created_at: string
  updated_at: string
  started_at?: string | null
  completed_at?: string | null
  requested_query_count: number
  executed_query_count: number
  step_results: WencaiIntersectionStepResult[]
  note?: string | null
  result?: WencaiIntersectionResponse | null
}

export type WatchlistItem = {
  id: number
  symbol: string
  display_name: string
  sector?: string | null
  tags: string[]
  note?: string | null
  created_at: string
  updated_at: string
}

export type WatchlistCreate = {
  symbol: string
  display_name: string
  sector?: string | null
  tags: string[]
  note?: string | null
}

export type WatchlistResponse = {
  items: WatchlistItem[]
}

export type SignalItem = {
  id: number
  snapshot_id: number
  watchlist_id: number
  symbol: string
  display_name: string
  score: number
  confidence: number
  action: string
  summary: string
  reasons: string[]
  created_at: string
}

export type SignalResponse = {
  items: SignalItem[]
}

export type SignalSyncResponse = {
  snapshot_id: number
  watchlist_count: number
  signal_count: number
  notes: string[]
  top_signals: SignalItem[]
}
