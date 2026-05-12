import { type FormEvent, useEffect, useMemo, useRef, useState } from 'react'

import {
  createWencaiIntersectionJob,
  createWatchlistItem,
  deleteWatchlistItem,
  fetchDashboard,
  fetchMarketSnapshot,
  fetchRealtimeQuote,
  fetchSignals,
  fetchWatchlist,
  fetchWencaiIntersectionJob,
  syncSignals,
} from './services/api'
import type {
  DashboardPayload,
  IntradayTrendResponse,
  MarketSnapshot,
  RealtimeQuoteResponse,
  SignalItem,
  WatchlistCreate,
  WencaiIntersectionJobCreateResponse,
  WencaiIntersectionJobResponse,
  WencaiIntersectionResponse,
  WatchlistItem,
} from './types'

type AppView = 'overview' | 'watchlist' | 'wencai' | 'todo'

const NAV_ITEMS: Array<{ id: AppView; label: string; hint: string }> = [
  { id: 'overview', label: '首页', hint: '热点板块 / 事件流 / 异动 / 龙虎榜' },
  { id: 'watchlist', label: '观察池', hint: '观察股票 / 腾讯快照 / 实时信号' },
  { id: 'wencai', label: '问财', hint: '自然语言筛选 / 预设语句 / 结果表格' },
  { id: 'todo', label: 'TODO', hint: '后续待办 / 阻塞项 / 工作台事项' },
]

const VIEW_META: Record<AppView, { badge: string; title: string; subtitle: string }> = {
  overview: {
    badge: 'Market Overview',
    title: '市场首页',
    subtitle: '首页只保留热点板块、事件流、市场异动和龙虎榜，方便快速观察当天市场脉搏。',
  },
  watchlist: {
    badge: 'Watchlist & Signals',
    title: '观察池与实时信号',
    subtitle: '把关心的股票加入观察池，查看腾讯实时快照，并手动同步实时信号评分。',
  },
  wencai: {
    badge: 'Wencai Screener',
    title: '问财自然语言筛选',
    subtitle: '按你选择的条件数量串行执行问财语句，自动做交集，并把交集结果批量写入观察池。',
  },
  todo: {
    badge: 'Execution TODO',
    title: '待办与推进面板',
    subtitle: '把后续开发事项、阻塞项和策略工作台计划单独拆出，避免首页信息过载。',
  },
}

type WencaiPreset = {
  id: string
  name: string
  description: string
  queries: string[]
  sortKey: string
  sortOrder: string
  queryType: string
  limit: string
  intervalSeconds: string
}

type WatchlistImportCandidate = {
  symbol: string
  displayName: string
  sector?: string | null
  tags?: string[]
  note?: string | null
}

const WENCAI_PRESETS: WencaiPreset[] = [
  {
    id: 'auction-three-way',
    name: '竞价三交集模板',
    description: '把你的主板竞价首板条件拆成三个问财请求，最后按股票代码做交集。',
    queries: [
      '沪深主板且非ST且价格小于23',
      '近10年涨停总数大于16，昨日首板涨停且11:30前涨停',
      '竞价涨跌幅>3%<9%',
    ],
    sortKey: '涨停次数',
    sortOrder: 'desc',
    queryType: 'stock',
    limit: '20',
    intervalSeconds: '90',
  },
  {
    id: 'delisted',
    name: '退市股票',
    description: '三个请求都指向退市股票，适合验证 Cookie 与交集流程是否正常。',
    queries: ['退市股票', '退市股票', '退市股票'],
    sortKey: '退市@退市日期',
    sortOrder: 'asc',
    queryType: 'stock',
    limit: '20',
    intervalSeconds: '90',
  },
]
const WENCAI_QUERY_COUNT_OPTIONS = Array.from({ length: 12 }, (_, index) => index + 1)
const WENCAI_CUSTOM_PRESET_STORAGE_KEY = 'stock:wencai-custom-presets'

const WENCAI_DISPLAY_FIELD_RULES: Array<{ label: string; patterns: string[] }> = [
  { label: '股票代码', patterns: ['股票代码', 'code'] },
  { label: '股票简称', patterns: ['股票简称', '简称', '股票名称'] },
  { label: '收盘价', patterns: ['收盘价', 'close'] },
  { label: '当日涨停价', patterns: ['当日涨停价', '涨停价'] },
  { label: '9.95%价格', patterns: ['9.95%价格', '当日涨到9.95%时价格'] },
  { label: '开盘价', patterns: ['开盘价', '今开', 'open'] },
  { label: '最高价', patterns: ['最高价', 'high'] },
  { label: '最低价', patterns: ['最低价', 'low'] },
]
const WENCAI_CODE_PATTERNS = ['股票代码', 'code']
const WENCAI_NAME_PATTERNS = ['股票简称', '简称', '股票名称']

function clampWencaiQueryCount(value: number): number {
  if (!Number.isFinite(value)) {
    return 1
  }
  return Math.min(12, Math.max(1, Math.trunc(value)))
}

function resizeWencaiQueries(queries: string[], targetCount: number): string[] {
  const normalizedCount = clampWencaiQueryCount(targetCount)
  const nextQueries = queries.slice(0, normalizedCount)
  while (nextQueries.length < normalizedCount) {
    nextQueries.push('')
  }
  return nextQueries
}

function parseStoredWencaiPresets(raw: string | null): WencaiPreset[] {
  if (!raw) {
    return []
  }

  try {
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) {
      return []
    }

    return parsed.flatMap((item, index) => {
      if (!item || typeof item !== 'object') {
        return []
      }

      const record = item as Record<string, unknown>
      const name = typeof record.name === 'string' ? record.name.trim() : ''
      if (!name) {
        return []
      }

      const queries = Array.isArray(record.queries)
        ? resizeWencaiQueries(record.queries.map((query) => String(query ?? '')), record.queries.length || 1)
        : ['']

      return [{
        id: typeof record.id === 'string' && record.id.trim() ? record.id : `custom-${index}`,
        name,
        description: typeof record.description === 'string' ? record.description : '',
        queries,
        sortKey: typeof record.sortKey === 'string' ? record.sortKey : '',
        sortOrder: typeof record.sortOrder === 'string' ? record.sortOrder : 'desc',
        queryType: typeof record.queryType === 'string' ? record.queryType : 'stock',
        limit: typeof record.limit === 'string' ? record.limit : '20',
        intervalSeconds: typeof record.intervalSeconds === 'string' ? record.intervalSeconds : '90',
      }]
    })
  } catch {
    return []
  }
}

function loadStoredWencaiPresets(): WencaiPreset[] {
  if (typeof window === 'undefined') {
    return []
  }

  try {
    return parseStoredWencaiPresets(window.localStorage.getItem(WENCAI_CUSTOM_PRESET_STORAGE_KEY))
  } catch {
    return []
  }
}

function createWencaiFormFromPreset(preset: WencaiPreset) {
  return {
    queries: resizeWencaiQueries(preset.queries, preset.queries.length),
    sortKey: preset.sortKey,
    sortOrder: preset.sortOrder,
    limit: preset.limit,
    queryType: preset.queryType,
    intervalSeconds: preset.intervalSeconds,
  }
}

function inferExchangeFromDigits(digits: string): string {
  if (digits.length === 5) {
    return 'HK'
  }
  if (/^[569]/.test(digits)) {
    return 'SH'
  }
  if (/^[48]/.test(digits)) {
    return 'BJ'
  }
  return 'SZ'
}

function normalizeSymbol(symbol: string): string {
  const raw = symbol.trim().toUpperCase().replace(/\s+/g, '')
  if (!raw) {
    return ''
  }

  const tsCodeMatch = raw.match(/^(\d{5,6})\.(SH|SZ|BJ|HK)$/)
  if (tsCodeMatch) {
    return `${tsCodeMatch[1]}.${tsCodeMatch[2]}`
  }

  const prefixedMatch = raw.match(/^(SH|SZ|BJ|HK)(\d{5,6})$/)
  if (prefixedMatch) {
    return `${prefixedMatch[2]}.${prefixedMatch[1]}`
  }

  if (/^\d{5,6}$/.test(raw)) {
    return `${raw}.${inferExchangeFromDigits(raw)}`
  }

  const digits = raw.replace(/\D/g, '')
  if (/^\d{5,6}$/.test(digits)) {
    return `${digits}.${inferExchangeFromDigits(digits)}`
  }

  return raw
}

function normalizeFieldKey(key: string): string {
  return key.replace(/\s+/g, '').toLowerCase()
}

function pickWencaiFieldValue(row: Record<string, unknown>, patterns: string[]): unknown | null {
  const matchedEntry = Object.entries(row).find(([key]) => {
    const normalizedKey = normalizeFieldKey(key)
    return patterns.some((pattern) => normalizedKey.includes(normalizeFieldKey(pattern)))
  })
  return matchedEntry ? matchedEntry[1] : null
}

function extractWencaiWatchCandidate(row: Record<string, unknown>): { symbol: string; displayName: string } | null {
  const symbolValue = pickWencaiFieldValue(row, WENCAI_CODE_PATTERNS)
  const nameValue = pickWencaiFieldValue(row, WENCAI_NAME_PATTERNS)
  const symbol = normalizeSymbol(formatWencaiCell(symbolValue))
  const displayName = formatWencaiCell(nameValue).trim()

  if (!symbol || !displayName || displayName === '--') {
    return null
  }

  return {
    symbol,
    displayName,
  }
}

function buildWencaiIntersectionWatchNote(queries: string[]): string {
  const normalizedQueries = queries
    .map((query, index) => `${index + 1}. ${query.replace(/\s+/g, ' ').trim()}`)
    .filter((item) => item && !item.endsWith('. '))
  const note = `问财交集：${normalizedQueries.join(' | ')}`
  return note.length > 360 ? `${note.slice(0, 357)}...` : note
}

function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '--'
  }
  return value.toFixed(digits)
}

function formatSignedPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '--'
  }
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

function formatSignedNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '--'
  }
  return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}`
}

function buildTrendPaths(points: IntradayTrendResponse['points'], width: number, height: number, padding: number) {
  if (!points.length) {
    return { linePath: '', areaPath: '', minPrice: null, maxPrice: null }
  }

  const prices = points.map((point) => point.close)
  const minPrice = Math.min(...prices)
  const maxPrice = Math.max(...prices)
  const range = maxPrice - minPrice || 1
  const innerWidth = width - padding * 2
  const innerHeight = height - padding * 2

  const coordinates = points.map((point, index) => {
    const x = padding + (index / Math.max(points.length - 1, 1)) * innerWidth
    const y = padding + ((maxPrice - point.close) / range) * innerHeight
    return { x, y }
  })

  const linePath = coordinates.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ')
  const areaPath = `${linePath} L ${coordinates[coordinates.length - 1].x} ${height - padding} L ${coordinates[0].x} ${height - padding} Z`

  return { linePath, areaPath, minPrice, maxPrice }
}

function buildDisabledTrend(symbol: string): IntradayTrendResponse {
  return {
    symbol,
    source: 'disabled',
    supported: false,
    points: [],
    note: '当前版本暂未启用分钟线 / 分时走势。',
  }
}

function pickWencaiDisplayColumns(columns: string[]): string[] {
  const normalizedEntries = columns.map((column) => ({
    raw: column,
    normalized: column.replace(/\s+/g, '').toLowerCase(),
  }))

  const picked: string[] = []
  for (const rule of WENCAI_DISPLAY_FIELD_RULES) {
    const match = normalizedEntries.find((entry) =>
      rule.patterns.some((pattern) => entry.normalized.includes(pattern.replace(/\s+/g, '').toLowerCase())),
    )
    if (match && !picked.includes(match.raw)) {
      picked.push(match.raw)
    }
  }

  return picked
}

function formatWencaiCell(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return '--'
  }

  if (typeof value === 'number') {
    return Number.isFinite(value) ? String(value) : '--'
  }

  if (typeof value === 'boolean') {
    return value ? 'true' : 'false'
  }

  if (Array.isArray(value)) {
    return value.map((item) => formatWencaiCell(item)).join(' / ')
  }

  if (typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch {
      return '[object]'
    }
  }

  return String(value)
}

function App() {
  const presetCardRefs = useRef<Record<string, HTMLDivElement | null>>({})
  const [activeView, setActiveView] = useState<AppView>('overview')
  const [data, setData] = useState<DashboardPayload | null>(null)
  const [market, setMarket] = useState<MarketSnapshot | null>(null)
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([])
  const [signals, setSignals] = useState<SignalItem[]>([])
  const [selectedWatchSymbol, setSelectedWatchSymbol] = useState<string | null>(null)
  const [watchTrend, setWatchTrend] = useState<IntradayTrendResponse | null>(null)
  const [watchQuotesBySymbol, setWatchQuotesBySymbol] = useState<Record<string, RealtimeQuoteResponse>>({})
  const [quoteLoading, setQuoteLoading] = useState(false)
  const [refreshingAllWatchQuotes, setRefreshingAllWatchQuotes] = useState(false)
  const [watchRealtimeMessage, setWatchRealtimeMessage] = useState<string | null>(null)
  const [addingWatchSymbols, setAddingWatchSymbols] = useState<string[]>([])
  const [syncNotes, setSyncNotes] = useState<string[]>([])
  const [syncing, setSyncing] = useState(false)
  const [customWencaiPresets, setCustomWencaiPresets] = useState<WencaiPreset[]>(loadStoredWencaiPresets)
  const [selectedPresetId, setSelectedPresetId] = useState<string>(WENCAI_PRESETS[0].id)
  const [savedPresetHighlight, setSavedPresetHighlight] = useState<{ id: string; token: number } | null>(null)
  const [wencaiForm, setWencaiForm] = useState(() => createWencaiFormFromPreset(WENCAI_PRESETS[0]))
  const [wencaiPresetDraft, setWencaiPresetDraft] = useState({
    name: '',
    description: '',
  })
  const [wencaiResult, setWencaiResult] = useState<WencaiIntersectionResponse | null>(null)
  const [wencaiLoading, setWencaiLoading] = useState(false)
  const [wencaiJob, setWencaiJob] = useState<WencaiIntersectionJobResponse | null>(null)
  const [wencaiSubmittedJob, setWencaiSubmittedJob] = useState<WencaiIntersectionJobCreateResponse | null>(null)
  const [form, setForm] = useState({
    symbol: '',
    display_name: '',
    sector: '',
    tags: '',
    note: '',
  })

  async function refreshCoreData() {
    const [dashboard, snapshot, watchlistResponse, signalResponse] = await Promise.all([
      fetchDashboard(),
      fetchMarketSnapshot(),
      fetchWatchlist(),
      fetchSignals(),
    ])
    setData(dashboard)
    setMarket(snapshot)
    setWatchlist(watchlistResponse.items)
    setSignals(signalResponse.items)
  }

  async function refreshWatchRealtime(symbol: string) {
    setQuoteLoading(true)
    try {
      const quoteResponse = await fetchRealtimeQuote(symbol)
      const normalizedSymbol = normalizeSymbol(symbol)
      setWatchQuotesBySymbol((prev) => ({
        ...prev,
        [normalizedSymbol || symbol]: quoteResponse,
      }))
      setWatchTrend(buildDisabledTrend(symbol))
    } finally {
      setQuoteLoading(false)
    }
  }

  async function refreshAllWatchRealtime(items: WatchlistItem[] = watchlist) {
    if (!items.length) {
      setWatchQuotesBySymbol({})
      setWatchRealtimeMessage('观察池为空，暂无可刷新的实时快照。')
      return
    }

    setRefreshingAllWatchQuotes(true)
    try {
      const quoteEntries = await Promise.all(
        items.map(async (item) => {
          const normalizedSymbol = normalizeSymbol(item.symbol) || item.symbol
          const quote = await fetchRealtimeQuote(item.symbol)
          return [normalizedSymbol, quote] as const
        }),
      )

      const nextQuotes = Object.fromEntries(quoteEntries) as Record<string, RealtimeQuoteResponse>
      setWatchQuotesBySymbol(nextQuotes)

      const totalCount = quoteEntries.length
      const successCount = Object.values(nextQuotes).filter((quote) => quote.supported).length
      const failedCount = totalCount - successCount
      setWatchRealtimeMessage(
        failedCount
          ? `已触发 ${totalCount} 只观察股票的实时快照，成功 ${successCount}，失败 ${failedCount}。`
          : `已触发全部 ${totalCount} 只观察股票的腾讯实时快照。`,
      )
    } finally {
      setRefreshingAllWatchQuotes(false)
    }
  }

  useEffect(() => {
    void refreshCoreData()
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') {
      return
    }

    window.localStorage.setItem(WENCAI_CUSTOM_PRESET_STORAGE_KEY, JSON.stringify(customWencaiPresets))
  }, [customWencaiPresets])

  useEffect(() => {
    if (!savedPresetHighlight) {
      return
    }

    const targetCard = presetCardRefs.current[savedPresetHighlight.id]
    if (targetCard) {
      targetCard.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      })
    }

    const timeoutId = window.setTimeout(() => {
      setSavedPresetHighlight((current) =>
        current?.token === savedPresetHighlight.token ? null : current,
      )
    }, 2400)

    return () => window.clearTimeout(timeoutId)
  }, [savedPresetHighlight])

  useEffect(() => {
    if (!watchlist.length) {
      setSelectedWatchSymbol(null)
      setWatchTrend(null)
      setWatchQuotesBySymbol({})
      setWatchRealtimeMessage(null)
      return
    }

    setWatchQuotesBySymbol((prev) => {
      const activeSymbols = new Set(watchlist.map((item) => normalizeSymbol(item.symbol)))
      const nextEntries = Object.entries(prev).filter(([symbol]) => activeSymbols.has(symbol))
      if (nextEntries.length === Object.keys(prev).length) {
        return prev
      }
      return Object.fromEntries(nextEntries)
    })

    if (!selectedWatchSymbol || !watchlist.some((item) => item.symbol === selectedWatchSymbol)) {
      setSelectedWatchSymbol(watchlist[0].symbol)
    }
  }, [watchlist, selectedWatchSymbol])

  useEffect(() => {
    if (!selectedWatchSymbol) {
      setWatchTrend(null)
      return
    }

    setWatchTrend(buildDisabledTrend(selectedWatchSymbol))
  }, [selectedWatchSymbol])

  useEffect(() => {
    if (activeView !== 'watchlist' || !watchlist.length) {
      return
    }

    void refreshAllWatchRealtime(watchlist)
  }, [activeView])

  useEffect(() => {
    if (activeView !== 'watchlist' || !selectedWatchSymbol) {
      return
    }

    if (refreshingAllWatchQuotes || watchQuotesBySymbol[normalizeSymbol(selectedWatchSymbol)]) {
      return
    }

    void refreshWatchRealtime(selectedWatchSymbol)
  }, [activeView, refreshingAllWatchQuotes, selectedWatchSymbol, watchQuotesBySymbol])

  useEffect(() => {
    if (activeView !== 'watchlist' || !watchlist.length) {
      return
    }

    const intervalId = window.setInterval(() => {
      void refreshAllWatchRealtime(watchlist)
    }, 15000)

    return () => window.clearInterval(intervalId)
  }, [activeView, watchlist])

  useEffect(() => {
    const pollingJobId = wencaiSubmittedJob?.job_id
    if (!pollingJobId) {
      return
    }

    let cancelled = false
    let timeoutId: number | null = null

    const pollJob = async () => {
      try {
        const job = await fetchWencaiIntersectionJob(pollingJobId)
        if (cancelled) {
          return
        }

        setWencaiJob(job)
        if (job.result) {
          setWencaiResult(job.result)
        }

        if (job.status === 'succeeded' || job.status === 'failed') {
          setWencaiLoading(false)
          setWencaiSubmittedJob(null)

          const watchlistResponse = await fetchWatchlist()
          if (cancelled) {
            return
          }
          setWatchlist(watchlistResponse.items)
          if (watchlistResponse.items.length) {
            await refreshAllWatchRealtime(watchlistResponse.items)
          }

          if (job.note) {
            setWatchRealtimeMessage(job.note)
          }
          return
        }

        timeoutId = window.setTimeout(pollJob, (wencaiSubmittedJob?.poll_after_seconds ?? 5) * 1000)
      } catch (error) {
        if (cancelled) {
          return
        }

        setWencaiLoading(false)
        setWencaiSubmittedJob(null)
        setWencaiJob((prev) => prev ?? {
          job_id: pollingJobId,
          status: 'failed',
          created_at: '',
          updated_at: '',
          requested_query_count: 0,
          executed_query_count: 0,
          step_results: [],
          note: error instanceof Error ? error.message : '问财任务轮询失败。',
          result: null,
        })
      }
    }

    void pollJob()

    return () => {
      cancelled = true
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId)
      }
    }
  }, [wencaiSubmittedJob])

  const selectedWatchItem = useMemo(
    () => watchlist.find((item) => item.symbol === selectedWatchSymbol) ?? null,
    [watchlist, selectedWatchSymbol],
  )

  const watchlistBySymbol = useMemo(
    () =>
      watchlist.reduce<Record<string, WatchlistItem>>((result, item) => {
        result[normalizeSymbol(item.symbol)] = item
        return result
      }, {}),
    [watchlist],
  )

  const watchQuote = useMemo(() => {
    if (!selectedWatchSymbol) {
      return null
    }
    return watchQuotesBySymbol[normalizeSymbol(selectedWatchSymbol)] ?? null
  }, [selectedWatchSymbol, watchQuotesBySymbol])

  const selectedSignals = useMemo(() => {
    if (!selectedWatchSymbol) {
      return signals
    }
    const matched = signals.filter((item) => item.symbol === selectedWatchSymbol)
    return matched.length ? matched : signals
  }, [signals, selectedWatchSymbol])

  const trendGeometry = useMemo(
    () => buildTrendPaths(watchTrend?.points ?? [], 720, 260, 22),
    [watchTrend],
  )

  const wencaiColumns = useMemo(() => {
    if (wencaiResult?.columns?.length) {
      return wencaiResult.columns
    }
    return wencaiResult?.items[0] ? Object.keys(wencaiResult.items[0]) : []
  }, [wencaiResult])

  const wencaiDisplayColumns = useMemo(
    () => pickWencaiDisplayColumns(wencaiColumns),
    [wencaiColumns],
  )

  const allWencaiPresets = useMemo(
    () => [...WENCAI_PRESETS, ...customWencaiPresets],
    [customWencaiPresets],
  )

  const todoSections = useMemo(() => {
    if (!data) {
      return []
    }

    return [
      {
        title: '优先待办',
        caption: 'Next Up',
        items: data.migration.next_up,
      },
      {
        title: '工作台事项',
        caption: 'Strategy Workbench',
        items: data.strategy_workbench.map((item) => `${item.name} · ${item.note}`),
      },
      {
        title: '阻塞与依赖',
        caption: 'Blockers',
        items: data.migration.blockers,
      },
    ]
  }, [data])

  if (!data || !market) {
    return <div className="page loading">Loading dashboard...</div>
  }

  async function importWatchlistCandidates(
    candidates: WatchlistImportCandidate[],
    options: { activateWatchlist?: boolean; refreshQuotes?: boolean } = {},
  ) {
    const dedupedCandidates = Array.from(
      candidates.reduce<Map<string, WatchlistImportCandidate>>((result, candidate) => {
        const normalizedSymbol = normalizeSymbol(candidate.symbol)
        if (!normalizedSymbol) {
          return result
        }

        if (!result.has(normalizedSymbol)) {
          result.set(normalizedSymbol, {
            ...candidate,
            symbol: normalizedSymbol,
          })
        }
        return result
      }, new Map()),
    ).map(([, candidate]) => candidate)

    if (options.activateWatchlist) {
      setActiveView('watchlist')
    }

    if (!dedupedCandidates.length) {
      return {
        items: watchlist,
        addedCount: 0,
        existingCount: 0,
      }
    }

    const existingSymbols = new Set(Object.keys(watchlistBySymbol))
    let addedCount = 0
    let existingCount = 0

    for (const candidate of dedupedCandidates) {
      if (existingSymbols.has(candidate.symbol)) {
        existingCount += 1
        continue
      }

      await createWatchlistItem({
        symbol: candidate.symbol,
        display_name: candidate.displayName,
        sector: candidate.sector ?? null,
        tags: candidate.tags ?? [],
        note: candidate.note ?? null,
      })
      existingSymbols.add(candidate.symbol)
      addedCount += 1
    }

    const items = addedCount ? (await fetchWatchlist()).items : watchlist
    if (addedCount) {
      setWatchlist(items)
    }

    const firstImportedSymbol = dedupedCandidates[0]?.symbol
    if (firstImportedSymbol) {
      const selectedItem = items.find((item) => normalizeSymbol(item.symbol) === firstImportedSymbol)
      if (selectedItem) {
        setSelectedWatchSymbol(selectedItem.symbol)
      }
    }

    if (options.refreshQuotes !== false && items.length) {
      await refreshAllWatchRealtime(items)
    }

    return {
      items,
      addedCount,
      existingCount,
    }
  }

  async function addWatchlistItemAndRefresh(
    payload: WatchlistCreate,
    options: { activateWatchlist?: boolean } = {},
  ) {
    const normalizedSymbol = normalizeSymbol(payload.symbol) || payload.symbol.trim().toUpperCase()
    const existingItem = watchlistBySymbol[normalizedSymbol]
    const { items, addedCount } = await importWatchlistCandidates(
      [{
        symbol: normalizedSymbol,
        displayName: payload.display_name,
        sector: payload.sector ?? null,
        tags: payload.tags,
        note: payload.note ?? null,
      }],
      { activateWatchlist: options.activateWatchlist, refreshQuotes: true },
    )

    const nextSelectedItem = items.find((item) => normalizeSymbol(item.symbol) === normalizedSymbol) ?? existingItem ?? null
    if (nextSelectedItem) {
      setSelectedWatchSymbol(nextSelectedItem.symbol)
      setWatchRealtimeMessage(
        addedCount
          ? `已将 ${nextSelectedItem.display_name} 加入观察池，并触发全部实时快照。`
          : `${nextSelectedItem.display_name} 已在观察池中，已重新触发全部实时快照。`,
      )
    }
    return nextSelectedItem
  }

  async function handleCreateWatchlist(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!form.symbol.trim() || !form.display_name.trim()) {
      return
    }

    try {
      await addWatchlistItemAndRefresh({
        symbol: form.symbol.trim(),
        display_name: form.display_name.trim(),
        sector: form.sector.trim() || null,
        tags: form.tags.split(',').map((item) => item.trim()).filter(Boolean),
        note: form.note.trim() || null,
      })

      setForm({
        symbol: '',
        display_name: '',
        sector: '',
        tags: '',
        note: '',
      })
    } catch (error) {
      setWatchRealtimeMessage(
        `加入观察池失败：${error instanceof Error ? error.message : '请检查后端日志。'}`,
      )
    }
  }

  async function handleDeleteWatchlist(itemId: number) {
    const removedItem = watchlist.find((item) => item.id === itemId)
    try {
      await deleteWatchlistItem(itemId)
      const response = await fetchWatchlist()
      setWatchlist(response.items)

      if (!response.items.length) {
        setWatchQuotesBySymbol({})
        setWatchRealtimeMessage('观察池已清空。')
        return
      }

      setWatchRealtimeMessage(`已删除 ${removedItem?.display_name ?? '观察项'}，并刷新剩余观察池快照。`)
      if (activeView === 'watchlist') {
        await refreshAllWatchRealtime(response.items)
      }
    } catch (error) {
      setWatchRealtimeMessage(
        `删除观察池失败：${error instanceof Error ? error.message : '请检查后端日志。'}`,
      )
    }
  }

  async function handleSyncSignals() {
    setSyncing(true)
    try {
      const response = await syncSignals()
      setSyncNotes(response.notes)
      const [signalResponse, snapshot] = await Promise.all([
        fetchSignals(),
        fetchMarketSnapshot(),
      ])
      setSignals(signalResponse.items)
      setMarket(snapshot)
      if (watchlist.length) {
        await refreshAllWatchRealtime(watchlist)
      }
    } finally {
      setSyncing(false)
    }
  }

  async function handleAddWencaiToWatchlist(candidate: { symbol: string; displayName: string }) {
    const normalizedSymbol = normalizeSymbol(candidate.symbol)
    setAddingWatchSymbols((prev) =>
      prev.includes(normalizedSymbol) ? prev : [...prev, normalizedSymbol],
    )

    try {
      await addWatchlistItemAndRefresh(
        {
          symbol: normalizedSymbol,
          display_name: candidate.displayName,
          sector: null,
          tags: ['问财'],
          note: buildWencaiIntersectionWatchNote(wencaiForm.queries),
        },
        { activateWatchlist: true },
      )
    } catch (error) {
      setWatchRealtimeMessage(
        `问财结果加入观察池失败：${error instanceof Error ? error.message : '请检查后端日志。'}`,
      )
    } finally {
      setAddingWatchSymbols((prev) => prev.filter((item) => item !== normalizedSymbol))
    }
  }

  function applyWencaiPreset(preset: WencaiPreset) {
    setSelectedPresetId(preset.id)
    setWencaiForm(createWencaiFormFromPreset(preset))
    setWencaiPresetDraft({
      name: preset.name,
      description: preset.description,
    })
    setWencaiJob(null)
    setWencaiResult(null)
    setWatchRealtimeMessage(`已载入内置语句：${preset.name}`)
  }

  function handleWencaiQueryCountChange(nextCount: number) {
    setSelectedPresetId('')
    setWencaiForm((prev) => ({
      ...prev,
      queries: resizeWencaiQueries(prev.queries, nextCount),
    }))
  }

  function handleRemoveWencaiQueryBox(indexToRemove: number) {
    setSelectedPresetId('')
    setWencaiForm((prev) => {
      if (prev.queries.length <= 1) {
        return prev
      }

      return {
        ...prev,
        queries: prev.queries.filter((_, index) => index !== indexToRemove),
      }
    })
  }

  function handleSaveCustomWencaiPreset() {
    const name = wencaiPresetDraft.name.trim()
    if (!name) {
      setWatchRealtimeMessage('请先填写内置语句名称后再保存。')
      return
    }

    const presetId = selectedPresetId.startsWith('custom-')
      ? selectedPresetId
      : `custom-${Date.now()}`

    const nextPreset: WencaiPreset = {
      id: presetId,
      name,
      description: wencaiPresetDraft.description.trim() || '自定义内置语句',
      queries: resizeWencaiQueries(wencaiForm.queries, wencaiForm.queries.length),
      sortKey: wencaiForm.sortKey,
      sortOrder: wencaiForm.sortOrder,
      queryType: wencaiForm.queryType,
      limit: wencaiForm.limit,
      intervalSeconds: wencaiForm.intervalSeconds,
    }

    setCustomWencaiPresets((prev) => {
      const existingIndex = prev.findIndex((item) => item.id === presetId)
      if (existingIndex === -1) {
        return [...prev, nextPreset]
      }

      const next = [...prev]
      next[existingIndex] = nextPreset
      return next
    })
    setSelectedPresetId(presetId)
    setSavedPresetHighlight({
      id: presetId,
      token: Date.now(),
    })
    setWatchRealtimeMessage(`已保存自定义内置语句：${name}`)
  }

  function handleDeleteCustomWencaiPreset(presetId: string) {
    const preset = customWencaiPresets.find((item) => item.id === presetId)
    setCustomWencaiPresets((prev) => prev.filter((item) => item.id !== presetId))

    if (selectedPresetId === presetId) {
      setSelectedPresetId(WENCAI_PRESETS[0].id)
      setWencaiForm(createWencaiFormFromPreset(WENCAI_PRESETS[0]))
      setWencaiPresetDraft({
        name: WENCAI_PRESETS[0].name,
        description: WENCAI_PRESETS[0].description,
      })
    }

    setWatchRealtimeMessage(`已删除自定义内置语句：${preset?.name ?? '未命名模板'}`)
  }

  async function handleWencaiSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const queries = wencaiForm.queries.map((query) => query.trim()).filter(Boolean)
    if (!queries.length) {
      setWencaiResult({
        query: '',
        sort_key: wencaiForm.sortKey.trim() || null,
        sort_order: wencaiForm.sortOrder.trim() || null,
        query_type: wencaiForm.queryType.trim() || 'stock',
        source: 'pywencai-intersection',
        supported: false,
        columns: [],
        items: [],
        requested_query_count: 0,
        executed_query_count: 0,
        intersection_count: 0,
        watchlist_added_count: 0,
        watchlist_existing_count: 0,
        step_results: [],
        note: '至少填写 1 条问财语句后再运行交集筛选。',
      })
      return
    }

    setWencaiLoading(true)
    try {
      setWencaiJob(null)
      setWencaiResult(null)
      const job = await createWencaiIntersectionJob({
        queries,
        sort_key: wencaiForm.sortKey.trim() || null,
        sort_order: wencaiForm.sortOrder.trim() || null,
        limit: Number.parseInt(wencaiForm.limit, 10) || 20,
        query_type: wencaiForm.queryType.trim() || 'stock',
        interval_seconds: Math.max(0, Number.parseInt(wencaiForm.intervalSeconds, 10) || 0),
        import_to_watchlist: true,
      })
      setWencaiJob({
        job_id: job.job_id,
        status: job.status,
        created_at: job.created_at,
        updated_at: job.created_at,
        requested_query_count: job.requested_query_count,
        executed_query_count: 0,
        step_results: [],
        note: job.note,
        result: null,
      })
      setWencaiSubmittedJob(job)
    } catch (error) {
      setWencaiLoading(false)
      setWencaiResult({
        query: queries.join(' ∩ '),
        sort_key: wencaiForm.sortKey.trim() || null,
        sort_order: wencaiForm.sortOrder.trim() || null,
        query_type: wencaiForm.queryType.trim() || 'stock',
        source: 'frontend-failure',
        supported: false,
        columns: [],
        items: [],
        requested_query_count: queries.length,
        executed_query_count: 0,
        intersection_count: 0,
        watchlist_added_count: 0,
        watchlist_existing_count: 0,
        step_results: [],
        note: error instanceof Error ? error.message : '创建问财后台任务失败。',
      })
    }
  }

  const viewMeta = VIEW_META[activeView]

  return (
    <div className="page">
      <header className="hero hero-compact">
        <div>
          <p className="eyebrow">STOCK / FastAPI / React</p>
          <h1>{viewMeta.title}</h1>
          <p className="subtitle">{viewMeta.subtitle}</p>
        </div>
        <div className="hero-badge">{viewMeta.badge}</div>
      </header>

      <nav className="view-tabs" aria-label="平台子界面">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`view-tab ${activeView === item.id ? 'view-tab-active' : ''}`}
            onClick={() => setActiveView(item.id)}
          >
            <strong>{item.label}</strong>
            <span>{item.hint}</span>
          </button>
        ))}
      </nav>

      {activeView === 'overview' ? (
        <>
          <section className="content-grid two-columns">
            <article className="panel">
              <div className="panel-header">
                <h2>热点板块</h2>
                <span>Market Pulse</span>
              </div>
              <div className="sector-list">
                {data.hot_sectors.map((sector) => (
                  <div key={`${sector.name}-${sector.source}`} className="sector-item">
                    <div>
                      <h3>{sector.name}</h3>
                      <p>{sector.thesis}</p>
                      <small>{sector.source || 'legacy'} {sector.code ? `· ${sector.code}` : ''}</small>
                    </div>
                    <div className="sector-meta">
                      <strong>{sector.change_pct}</strong>
                      <span>{sector.leader}</span>
                    </div>
                  </div>
                ))}
              </div>
            </article>

            <article className="panel">
              <div className="panel-header">
                <h2>事件流</h2>
                <span>Event Stream</span>
              </div>
              <div className="event-list">
                {data.event_stream.map((event) => (
                  <div key={`${event.title}-${event.timestamp}`} className="event-item">
                    <div className={`sentiment sentiment-${event.sentiment}`} />
                    <div>
                      <h3>{event.title}</h3>
                      <p>{event.summary}</p>
                      <small>{event.source} · {event.timestamp}</small>
                    </div>
                  </div>
                ))}
              </div>
            </article>
          </section>

          <section className="content-grid two-columns">
            <article className="panel">
              <div className="panel-header">
                <h2>市场异动</h2>
                <span>Anomalies</span>
              </div>
              <div className="event-list">
                {market.anomalies.map((item) => (
                  <div key={`${item.title}-${item.timestamp}`} className="event-item">
                    <div className={`sentiment sentiment-${item.anomaly_type.includes('涨') ? 'positive' : 'neutral'}`} />
                    <div>
                      <h3>{item.title}</h3>
                      <p>{item.summary}</p>
                      <small>{item.source} · {item.timestamp}</small>
                    </div>
                  </div>
                ))}
              </div>
            </article>

            <article className="panel">
              <div className="panel-header">
                <h2>龙虎榜</h2>
                <span>Longhubang</span>
              </div>
              <div className="longhubang-list">
                {market.longhubang.map((item) => (
                  <div key={`${item.stock_code}-${item.timestamp}-${item.reason}`} className="longhubang-item">
                    <div>
                      <h3>{item.stock_name || item.stock_code}</h3>
                      <p>{item.reason}</p>
                      <small>{item.stock_code} · {item.source} · {item.timestamp}</small>
                    </div>
                    <div className="sector-meta">
                      <strong>{item.net_amount}</strong>
                      <span>买 {item.buy_total}</span>
                    </div>
                  </div>
                ))}
              </div>
            </article>
          </section>
        </>
      ) : null}

      {activeView === 'watchlist' ? (
        <>
          <section className="content-grid watchlist-layout">
            <article className="panel">
              <div className="panel-header">
                <h2>观察池</h2>
                <span>Watchlist</span>
              </div>

              <form className="watchlist-form" onSubmit={handleCreateWatchlist}>
                <input
                  value={form.symbol}
                  onChange={(event) => setForm((prev) => ({ ...prev, symbol: event.target.value }))}
                  placeholder="股票代码，如 600519 / 600519.SH / SH600519"
                />
                <input
                  value={form.display_name}
                  onChange={(event) => setForm((prev) => ({ ...prev, display_name: event.target.value }))}
                  placeholder="名称，如 贵州茅台"
                />
                <input
                  value={form.sector}
                  onChange={(event) => setForm((prev) => ({ ...prev, sector: event.target.value }))}
                  placeholder="所属板块/行业"
                />
                <input
                  value={form.tags}
                  onChange={(event) => setForm((prev) => ({ ...prev, tags: event.target.value }))}
                  placeholder="标签，逗号分隔"
                />
                <textarea
                  value={form.note}
                  onChange={(event) => setForm((prev) => ({ ...prev, note: event.target.value }))}
                  placeholder="观察逻辑 / 交易笔记"
                  rows={3}
                />
                <button type="submit">加入观察池</button>
              </form>

              <div className="signal-toolbar watchlist-toolbar">
                <button
                  type="button"
                  onClick={() => void refreshAllWatchRealtime()}
                  disabled={!watchlist.length || refreshingAllWatchQuotes}
                >
                  {refreshingAllWatchQuotes ? '快照刷新中…' : '触发全部实时快照'}
                </button>
                <small>加入新股票后会自动拉取全部观察标的的腾讯实时快照，并持续每 15 秒刷新。</small>
              </div>

              {watchRealtimeMessage ? (
                <div className="empty-state quote-note">{watchRealtimeMessage}</div>
              ) : null}

              {watchlist.length ? (
                <div className="watchlist-cards">
                  {watchlist.map((item) => {
                    const active = item.symbol === selectedWatchSymbol
                    const quote = watchQuotesBySymbol[normalizeSymbol(item.symbol)]
                    return (
                      <div key={item.id} className={`watchlist-card ${active ? 'watchlist-card-active' : ''}`}>
                        <button
                          type="button"
                          className="watchlist-select"
                          onClick={() => setSelectedWatchSymbol(item.symbol)}
                        >
                          <div className="watchlist-card-body">
                            <h3>{item.display_name}</h3>
                            <p>{item.symbol} {item.sector ? `· ${item.sector}` : ''}</p>
                            {item.tags.length ? <small>{item.tags.join(' / ')}</small> : null}
                            <div className="watchlist-snapshot">
                              <strong
                                className={
                                  quote?.change_pct !== null && quote?.change_pct !== undefined
                                    ? (quote.change_pct >= 0 ? 'positive-text' : 'negative-text')
                                    : ''
                                }
                              >
                                {formatNumber(quote?.price)}
                              </strong>
                              <span>
                                {quote?.supported
                                  ? `${formatSignedPercent(quote.change_pct)} · ${quote.quote_time ?? '--'}`
                                  : (refreshingAllWatchQuotes ? '批量快照刷新中…' : quote?.note ?? '等待腾讯快照')}
                              </span>
                              <small>{quote?.source ?? 'tencent-qt'}</small>
                            </div>
                          </div>
                        </button>
                        <div className="watchlist-card-actions">
                          <button className="ghost-button" type="button" onClick={() => handleDeleteWatchlist(item.id)}>
                            删除
                          </button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div className="empty-state">先添加你关心的股票，后面才会展示实时快照与实时信号。</div>
              )}
            </article>

            <article className="panel">
              <div className="panel-header">
                <h2>实时快照</h2>
                <span>{selectedWatchItem ? `${selectedWatchItem.display_name} · ${selectedWatchItem.symbol}` : 'Realtime'}</span>
              </div>

              {selectedWatchItem ? (
                <>
                  <div className="trend-summary">
                    <div>
                      <span>最新价 / 来源</span>
                      <strong>{formatNumber(watchQuote?.price ?? watchTrend?.latest_price)}</strong>
                      <small>{watchQuote?.source ?? watchTrend?.source ?? '--'}</small>
                    </div>
                    <div>
                      <span>涨跌 / 涨跌幅</span>
                      <strong className={((watchQuote?.change_pct ?? watchTrend?.change_pct ?? 0) >= 0) ? 'positive-text' : 'negative-text'}>
                        {formatSignedNumber(watchQuote?.change)} / {formatSignedPercent(watchQuote?.change_pct ?? watchTrend?.change_pct)}
                      </strong>
                    </div>
                    <div>
                      <span>日内低 / 日内高</span>
                      <strong>
                        {formatNumber(watchQuote?.low_price ?? watchTrend?.day_low)} / {formatNumber(watchQuote?.high_price ?? watchTrend?.day_high)}
                      </strong>
                    </div>
                  </div>

                  <div className="quote-grid">
                    <div className="quote-card">
                      <span>盘口一档</span>
                      <strong>买一 {formatNumber(watchQuote?.bid_price_1)}</strong>
                      <small>量 {formatNumber(watchQuote?.bid_volume_1, 0)} 手</small>
                    </div>
                    <div className="quote-card">
                      <span>卖一价</span>
                      <strong>{formatNumber(watchQuote?.ask_price_1)}</strong>
                      <small>量 {formatNumber(watchQuote?.ask_volume_1, 0)} 手</small>
                    </div>
                    <div className="quote-card">
                      <span>成交量 / 成交额</span>
                      <strong>{formatNumber(watchQuote?.volume_hands, 0)} 手</strong>
                      <small>{formatNumber(watchQuote?.amount_wan, 0)} 万</small>
                    </div>
                    <div className="quote-card">
                      <span>更新时间</span>
                      <strong>{watchQuote?.quote_time ?? '--'}</strong>
                      <small>
                        {refreshingAllWatchQuotes
                          ? '观察池批量快照刷新中…'
                          : (quoteLoading ? '单票快照刷新中…' : '自动每 15 秒刷新观察池')}
                      </small>
                    </div>
                  </div>

                  {watchQuote?.order_flow ? (
                    <div className="order-flow">
                      <div className="panel-subtitle">腾讯盘口资金分布（优先来源）</div>
                      <div className="order-flow-grid">
                        <div className="order-flow-item">
                          <span>买盘大单</span>
                          <strong>{formatNumber(watchQuote.order_flow.buy_large, 3)}</strong>
                        </div>
                        <div className="order-flow-item">
                          <span>买盘小单</span>
                          <strong>{formatNumber(watchQuote.order_flow.buy_small, 3)}</strong>
                        </div>
                        <div className="order-flow-item">
                          <span>卖盘大单</span>
                          <strong>{formatNumber(watchQuote.order_flow.sell_large, 3)}</strong>
                        </div>
                        <div className="order-flow-item">
                          <span>卖盘小单</span>
                          <strong>{formatNumber(watchQuote.order_flow.sell_small, 3)}</strong>
                        </div>
                      </div>
                    </div>
                  ) : null}

                  {watchQuote?.note ? (
                    <div className="empty-state quote-note">{watchQuote.note}</div>
                  ) : null}

                  {quoteLoading ? (
                    <div className="empty-state">正在加载腾讯实时快照…</div>
                  ) : watchTrend?.supported && watchTrend.points.length ? (
                    <div className="trend-chart-shell">
                      <div className="panel-subtitle">当日分时走势（用于补充图线）</div>
                      <svg viewBox="0 0 720 260" className="trend-chart" role="img" aria-label={`${selectedWatchItem.display_name} 当日分时走势`}>
                        <defs>
                          <linearGradient id="trendFill" x1="0" x2="0" y1="0" y2="1">
                            <stop offset="0%" stopColor="rgba(79, 156, 255, 0.42)" />
                            <stop offset="100%" stopColor="rgba(79, 156, 255, 0.02)" />
                          </linearGradient>
                        </defs>
                        <path d={trendGeometry.areaPath} fill="url(#trendFill)" />
                        <path d={trendGeometry.linePath} fill="none" stroke="#6cb6ff" strokeWidth="3" strokeLinecap="round" />
                      </svg>
                      <div className="trend-axis">
                        <span>{watchTrend.points[0]?.time ?? '--'}</span>
                        <span>{watchTrend.points[Math.floor(watchTrend.points.length / 2)]?.time ?? '--'}</span>
                        <span>{watchTrend.points[watchTrend.points.length - 1]?.time ?? '--'}</span>
                      </div>
                    </div>
                  ) : (
                    <div className="empty-state">
                      {watchTrend?.note ?? '当前没有可展示的当日走势数据。'}
                    </div>
                  )}

                  {selectedWatchItem.note ? (
                    <div className="watch-note">
                      <span>观察备注</span>
                      <p>{selectedWatchItem.note}</p>
                    </div>
                  ) : null}
                </>
              ) : (
                <div className="empty-state">先从左侧选择一只观察股票，或先添加新的观察对象。</div>
              )}
            </article>
          </section>

          <section className="content-grid one-column">
            <article className="panel">
              <div className="panel-header">
                <h2>实时信号同步</h2>
                <span>Sync & Score</span>
              </div>

              <div className="signal-toolbar">
                <button type="button" onClick={handleSyncSignals} disabled={syncing}>
                  {syncing ? '同步中…' : '同步实时信号'}
                </button>
                <small>基于事件流 / 市场异动 / 龙虎榜 / 热点板块做规则评分</small>
              </div>

              {syncNotes.length ? (
                <ul className="note-list">
                  {syncNotes.map((note) => <li key={note}>{note}</li>)}
                </ul>
              ) : null}

              {selectedSignals.length ? (
                <div className="signal-list">
                  {selectedSignals.slice(0, 10).map((signal) => (
                    <div key={signal.id} className="signal-item">
                      <div>
                        <h3>{signal.display_name}</h3>
                        <p>{signal.summary}</p>
                        <small>{signal.symbol} · confidence {signal.confidence}</small>
                      </div>
                      <div className="signal-score">
                        <strong>{signal.score}</strong>
                        <span className={`status status-${signal.action}`}>{signal.action}</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty-state">还没有 signal。添加观察池后点击“同步实时信号”。</div>
              )}
            </article>
          </section>
        </>
      ) : null}

      {activeView === 'wencai' ? (
        <>
          <section className="content-grid wencai-layout">
            <article className="panel">
              <div className="panel-header">
                <h2>内置语句</h2>
                <span>{allWencaiPresets.length} Presets</span>
              </div>

              <div className="preset-list">
                {allWencaiPresets.map((preset) => {
                  const active = preset.id === selectedPresetId
                  const custom = preset.id.startsWith('custom-')
                  const saved = savedPresetHighlight?.id === preset.id
                  return (
                    <div
                      key={preset.id}
                      ref={(node) => {
                        presetCardRefs.current[preset.id] = node
                      }}
                      className={`preset-card ${active ? 'preset-card-active' : ''} ${saved ? 'preset-card-saved' : ''}`}
                    >
                      <button
                        type="button"
                        className="preset-card-main"
                        onClick={() => applyWencaiPreset(preset)}
                      >
                        <div className="preset-card-title-row">
                          <strong>{preset.name}</strong>
                          <span>{custom ? '自定义' : '内置'}</span>
                        </div>
                        <p>{preset.description}</p>
                        <div className="preset-query-list">
                          {preset.queries.map((query, index) => (
                            <small key={`${preset.id}-${index}`}>{index + 1}. {query || '未填写'}</small>
                          ))}
                        </div>
                      </button>
                      {custom ? (
                        <div className="preset-card-actions">
                          <button
                            type="button"
                            className="ghost-button preset-delete-button"
                            onClick={() => handleDeleteCustomWencaiPreset(preset.id)}
                          >
                            删除
                          </button>
                        </div>
                      ) : null}
                    </div>
                  )
                })}
              </div>
            </article>

            <article className="panel">
              <div className="panel-header">
                <h2>问财输入框</h2>
                <span>{wencaiForm.queries.length} Queries</span>
              </div>

              <form className="wencai-form" onSubmit={handleWencaiSubmit}>
                <div className="wencai-custom-preset-form">
                  <label>
                    <span>保存成内置语句名称</span>
                    <input
                      value={wencaiPresetDraft.name}
                      onChange={(event) => setWencaiPresetDraft((prev) => ({ ...prev, name: event.target.value }))}
                      placeholder="例如：主板首板竞价"
                    />
                  </label>
                  <label>
                    <span>说明</span>
                    <textarea
                      rows={3}
                      value={wencaiPresetDraft.description}
                      onChange={(event) => setWencaiPresetDraft((prev) => ({ ...prev, description: event.target.value }))}
                      placeholder="说明这个模板适合什么场景"
                    />
                  </label>
                  <div className="wencai-custom-preset-actions">
                    <button type="button" onClick={handleSaveCustomWencaiPreset}>
                      {selectedPresetId.startsWith('custom-') ? '更新当前自定义语句' : '保存当前输入为内置语句'}
                    </button>
                    <small>这里保存的是你右侧当前填写的全部条件、数量、排序、返回条数和间隔设置。</small>
                  </div>
                </div>

                <div className="wencai-toolbar wencai-toolbar-compact">
                  <label className="wencai-query-count-control">
                    <span>条件数量</span>
                    <select
                      value={String(wencaiForm.queries.length)}
                      onChange={(event) => handleWencaiQueryCountChange(Number.parseInt(event.target.value, 10) || 1)}
                    >
                      {WENCAI_QUERY_COUNT_OPTIONS.map((count) => (
                        <option key={count} value={count}>
                          {count} 个条件
                        </option>
                      ))}
                    </select>
                  </label>
                  <small>可自定义条件数量；后端会按顺序串行执行，并按股票代码求交集。</small>
                </div>

                <div className="wencai-query-stack">
                  {wencaiForm.queries.map((query, index) => (
                    <div key={`query-${index}`} className="wencai-query-row">
                      <label>
                        <span>问财条件 {index + 1}</span>
                        <textarea
                          rows={index === 0 ? 5 : 4}
                          value={query}
                          onChange={(event) => setWencaiForm((prev) => {
                            const nextQueries = [...prev.queries]
                            nextQueries[index] = event.target.value
                            return {
                              ...prev,
                              queries: nextQueries,
                            }
                          })}
                          placeholder={index === 0 ? '例如：沪深主板且非ST且价格小于23...' : `输入第 ${index + 1} 条问财语句`}
                        />
                      </label>
                      <button
                        type="button"
                        className="ghost-button query-remove-button"
                        onClick={() => handleRemoveWencaiQueryBox(index)}
                        disabled={wencaiForm.queries.length <= 1}
                      >
                        删除
                      </button>
                    </div>
                  ))}
                </div>

                <div className="wencai-form-grid">
                  <label>
                    <span>排序字段</span>
                    <input
                      value={wencaiForm.sortKey}
                      onChange={(event) => setWencaiForm((prev) => ({ ...prev, sortKey: event.target.value }))}
                      placeholder="如：涨停次数"
                    />
                  </label>
                  <label>
                    <span>排序方向</span>
                    <select
                      value={wencaiForm.sortOrder}
                      onChange={(event) => setWencaiForm((prev) => ({ ...prev, sortOrder: event.target.value }))}
                    >
                      <option value="desc">desc</option>
                      <option value="asc">asc</option>
                    </select>
                  </label>
                  <label>
                    <span>返回条数</span>
                    <input
                      type="number"
                      min={1}
                      max={100}
                      value={wencaiForm.limit}
                      onChange={(event) => setWencaiForm((prev) => ({ ...prev, limit: event.target.value }))}
                    />
                  </label>
                  <label>
                    <span>查询类型</span>
                    <input
                      value={wencaiForm.queryType}
                      onChange={(event) => setWencaiForm((prev) => ({ ...prev, queryType: event.target.value }))}
                      placeholder="stock"
                    />
                  </label>
                  <label>
                    <span>请求间隔（秒）</span>
                    <input
                      type="number"
                      min={0}
                      max={180}
                      value={wencaiForm.intervalSeconds}
                      onChange={(event) => setWencaiForm((prev) => ({ ...prev, intervalSeconds: event.target.value }))}
                      placeholder="90"
                    />
                  </label>
                </div>

                <div className="wencai-toolbar">
                  <button type="submit" disabled={wencaiLoading}>
                    {wencaiLoading ? '后端交集任务执行中…' : '后端执行问财交集并加入观察池'}
                  </button>
                  <small>当前整套条件、排序和查询类型都可以保存成自定义内置语句；后端会处理串行调度和等待间隔。</small>
                </div>
              </form>
            </article>
          </section>

          <section className="content-grid one-column">
            <article className="panel">
              <div className="panel-header">
                <h2>查询结果</h2>
                <span>
                  {wencaiJob
                    ? `job ${wencaiJob.status} · ${wencaiJob.executed_query_count}/${wencaiJob.requested_query_count}`
                    : (wencaiResult ? `${wencaiResult.items.length} intersection rows · ${wencaiResult.source}` : 'Intersection Result')}
                </span>
              </div>

              {wencaiJob ? (
                <div className="wencai-status">
                  <strong>任务状态：{wencaiJob.status}</strong>
                  <small>
                    job_id: {wencaiJob.job_id}
                    {wencaiJob.started_at ? ` · started ${wencaiJob.started_at}` : ''}
                    {wencaiJob.completed_at ? ` · completed ${wencaiJob.completed_at}` : ''}
                  </small>
                  {wencaiJob.note ? <small>{wencaiJob.note}</small> : null}
                </div>
              ) : null}

              {(wencaiJob?.step_results.length || wencaiResult?.step_results.length) ? (
                <ul className="note-list wencai-run-notes">
                  {(wencaiJob?.step_results.length ? wencaiJob.step_results : (wencaiResult?.step_results ?? [])).map((step, index) => (
                    <li key={`${step.query}-${index}`}>
                      第 {index + 1} 次：{step.query} · {step.supported ? `返回 ${step.item_count} 条` : '执行失败'}
                      {step.note ? ` · ${step.note}` : ''}
                    </li>
                  ))}
                </ul>
              ) : null}

              {wencaiResult ? (
                <>
                  <div className="wencai-meta">
                    <div>
                      <span>query intersection</span>
                      <strong>{wencaiResult.query}</strong>
                    </div>
                    <div>
                      <span>sort</span>
                      <strong>{wencaiResult.sort_key || '--'} / {wencaiResult.sort_order || '--'}</strong>
                    </div>
                    <div>
                      <span>status</span>
                      <strong className={wencaiResult.supported ? 'positive-text' : 'negative-text'}>
                        {wencaiResult.supported ? 'supported' : 'unsupported'}
                      </strong>
                    </div>
                    <div>
                      <span>watchlist import</span>
                      <strong>{wencaiResult.watchlist_added_count} new / {wencaiResult.watchlist_existing_count} existing</strong>
                    </div>
                  </div>

                  {wencaiResult.note ? (
                    <div className="empty-state quote-note">{wencaiResult.note}</div>
                  ) : null}

                  {wencaiResult.items.length && wencaiDisplayColumns.length ? (
                    <div className="wencai-table-shell">
                      <table className="wencai-table">
                        <thead>
                          <tr>
                            {wencaiDisplayColumns.map((column) => (
                              <th key={column}>{column}</th>
                            ))}
                            <th>操作</th>
                          </tr>
                        </thead>
                        <tbody>
                          {wencaiResult.items.map((row, index) => {
                            const candidate = extractWencaiWatchCandidate(row)
                            const candidateSymbol = candidate ? normalizeSymbol(candidate.symbol) : ''
                            const existingWatchItem = candidateSymbol ? watchlistBySymbol[candidateSymbol] : null
                            const adding = candidateSymbol ? addingWatchSymbols.includes(candidateSymbol) : false

                            return (
                              <tr key={`${index}-${String(row[wencaiDisplayColumns[0]] ?? 'row')}`}>
                                {wencaiDisplayColumns.map((column) => (
                                  <td key={`${index}-${column}`}>{formatWencaiCell(row[column])}</td>
                                ))}
                                <td>
                                  {candidate ? (
                                    <button
                                      type="button"
                                      className="ghost-button table-action-button"
                                      onClick={() => void handleAddWencaiToWatchlist(candidate)}
                                      disabled={adding}
                                    >
                                      {adding ? '加入中…' : (existingWatchItem ? '查看并刷新' : '加入观察池')}
                                    </button>
                                  ) : (
                                    <span className="empty-state">未识别代码</span>
                                  )}
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : wencaiResult.items.length ? (
                    <div className="empty-state">
                      当前问财结果里没有识别到「股票代码 / 股票简称 / 收盘价 / 当日涨停价 / 9.95%价格 / 开盘价 / 最高价 / 最低价」这些字段。
                    </div>
                  ) : (
                    <div className="empty-state">后端已执行全部问财请求，但当前交集为空。</div>
                  )}
                </>
              ) : (
                <div className="empty-state">
                  {wencaiLoading
                    ? '后台任务已创建，正在轮询执行状态…'
                    : '先填写至少 1 个问财条件框，然后点击“后端执行问财交集并加入观察池”。'}
                </div>
              )}
            </article>
          </section>
        </>
      ) : null}

      {activeView === 'todo' ? (
        <>
          <section className="content-grid two-columns">
            {todoSections.map((section) => (
              <article key={section.title} className="panel">
                <div className="panel-header">
                  <h2>{section.title}</h2>
                  <span>{section.caption}</span>
                </div>
                <ul className="todo-list">
                  {section.items.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </article>
            ))}
          </section>

          <section className="content-grid one-column">
            <article className="panel">
              <div className="panel-header">
                <h2>平台现状备注</h2>
                <span>Current State</span>
              </div>
              <div className="workbench-list">
                {data.platform_status.critical_findings.map((item) => (
                  <div key={item} className="workbench-item">
                    <div>
                      <h3>系统说明</h3>
                      <p>{item}</p>
                    </div>
                    <span className="status status-building">note</span>
                  </div>
                ))}
              </div>
            </article>
          </section>
        </>
      ) : null}
    </div>
  )
}

export default App
