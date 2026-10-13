import { useEffect, useState, type ReactNode } from "react";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  ChevronRight,
  Database,
  Layers3,
  RefreshCw,
  Sprout,
} from "lucide-react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Bar,
} from "recharts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  getJson,
  calculateCharts,
  type ChartResponse,
  type ChartRow,
  type Stock,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const WINDOWS = [5, 20, 60] as const;
const COLORS = { 5: "#c39545", 20: "#7484a4", 60: "#bd7363" };
const PERIODS = [
  { value: "3m", label: "近 3 月", months: 3 },
  { value: "6m", label: "近 6 月", months: 6 },
  { value: "1y", label: "近 1 年", months: 12 },
  { value: "3y", label: "近 3 年", months: 36 },
  { value: "all", label: "全部历史", months: 0 },
];
const number = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });
const money = (value: number) =>
  value.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
const percent = (value: number) =>
  `${value > 0 ? "+" : ""}${(value * 100).toFixed(2)}%`;
const compactVolume = (value: number) =>
  value >= 1e8
    ? `${(value / 1e8).toFixed(1)}亿`
    : `${(value / 1e4).toFixed(0)}万`;

function ChartTooltip({
  active,
  payload,
  label,
  unit = "price",
}: {
  active?: boolean;
  payload?: readonly {
    name?: string | number;
    value?: unknown;
    color?: string;
    dataKey?: string | number;
  }[];
  label?: unknown;
  unit?: "price" | "volume" | "percent";
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip text-xs">
      <div className="mono mb-3 text-muted-foreground">{String(label)}</div>
      {payload
        .filter((item) => typeof item.value === "number")
        .map((item) => (
          <div
            key={String(item.dataKey)}
            className="my-1.5 flex justify-between gap-6"
          >
            <span className="flex items-center gap-2">
              <span
                className="size-1.5 rounded-full"
                style={{ background: item.color }}
              />
              {item.name}
            </span>
            <span className="mono font-medium">
              {unit === "percent"
                ? `${(Number(item.value) * 100).toFixed(2)}%`
                : unit === "volume"
                  ? compactVolume(Number(item.value))
                  : money(Number(item.value))}
            </span>
          </div>
        ))}
    </div>
  );
}

function Plot({
  title,
  subtitle,
  children,
  legend,
  height = 240,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  legend?: ReactNode;
  height?: number;
}) {
  return (
    <Card className="gap-0 border-border/80 bg-card py-0 shadow-none">
      <div className="flex flex-wrap items-start justify-between gap-3 px-6 pt-5 pb-4">
        <div>
          <h2 className="text-sm font-semibold">{title}</h2>
          <p className="mt-1 text-[11px] text-muted-foreground">{subtitle}</p>
        </div>
        <div className="flex flex-wrap gap-4 text-[11px]">{legend}</div>
      </div>
      <CardContent className="px-2 pb-3 sm:px-4">
        <div
          style={{ height }}
          className="w-full"
          role="img"
          aria-label={`${title}，可悬停查看每日数值`}
        >
          {children}
        </div>
      </CardContent>
    </Card>
  );
}

function LegendItem({
  color,
  children,
  dashed = false,
}: {
  color: string;
  children: ReactNode;
  dashed?: boolean;
}) {
  return (
    <span className="flex items-center gap-1.5 text-muted-foreground">
      <span
        className="w-3.5 border-t-2"
        style={{
          borderColor: color,
          borderTopStyle: dashed ? "dashed" : "solid",
        }}
      />
      {children}
    </span>
  );
}

function Metric({
  label,
  value,
  detail,
  positive,
}: {
  label: string;
  value: string;
  detail: string;
  positive?: boolean;
}) {
  return (
    <div className="border-border px-6 py-5 first:pl-0 last:pr-0 sm:not-last:border-r">
      <p className="mb-2 text-xs text-muted-foreground">{label}</p>
      <p
        className={cn(
          "mono text-2xl tracking-tight",
          positive === true && "text-[#b55a4e]",
          positive === false && "text-primary",
        )}
      >
        {value}
      </p>
      <p className="mt-1.5 text-[10px] text-muted-foreground">{detail}</p>
    </div>
  );
}

export default function App() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [symbol, setSymbol] = useState("");
  const [response, setResponse] = useState<ChartResponse | null>(null);
  const [period, setPeriod] = useState("1y");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [adjustType, setAdjustType] = useState<"qfq" | "hfq">("hfq");
  const [windows, setWindows] = useState<number[]>([5, 20, 60]);
  const [loading, setLoading] = useState(true);
  const [listLoading, setListLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);

  const selected = stocks.find((stock) => stock.symbol === symbol);
  const requestedEnd = endDate || selected?.end_date || "";
  const months = PERIODS.find((item) => item.value === period)?.months ?? 0;
  let requestedStart = startDate || selected?.start_date || "";
  if (!startDate && requestedEnd && months) {
    const cutoff = new Date(`${requestedEnd}T00:00:00Z`);
    cutoff.setUTCMonth(cutoff.getUTCMonth() - months);
    requestedStart = cutoff.toISOString().slice(0, 10);
  }
  const priceLabel = adjustType === "hfq" ? "后复权" : "前复权";

  useEffect(() => {
    const controller = new AbortController();
    setError("");
    setListLoading(true);
    getJson<{ stocks: Stock[] }>(
      "/api/stocks?source=baostock",
      controller.signal,
    )
      .then((result) => {
        setStocks(result.stocks);
        setSymbol((current) =>
          result.stocks.some((stock) => stock.symbol === current)
            ? current
            : (result.stocks.find((stock) => stock.symbol === "sh.600519")
                ?.symbol ??
              result.stocks[0]?.symbol ??
              ""),
        );
        if (!result.stocks.length) {
          setError("还没有原始日线数据，请先同步股票行情。");
          setLoading(false);
        }
      })
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") {
          setError(reason.message);
          setLoading(false);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setListLoading(false);
      });
    return () => controller.abort();
  }, [revision]);

  useEffect(() => {
    if (!symbol || !requestedStart || !requestedEnd) return;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setResponse(null);
    calculateCharts(
      {
        source: "baostock",
        symbol,
        start_date: requestedStart,
        end_date: requestedEnd,
        adjust_type: adjustType,
        windows,
      },
      controller.signal,
    )
      .then(setResponse)
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") setError(reason.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [symbol, revision, requestedStart, requestedEnd, adjustType, windows]);

  const data = response?.data ?? [];
  const latest = data.at(-1);
  const first = data[0];
  const rangeReturn = latest && first ? latest.close / first.close - 1 : 0;
  const change = latest?.daily_return ?? 0;
  const legend = (prefix: string) =>
    WINDOWS.filter((window) => windows.includes(window)).map((window) => (
      <LegendItem key={window} color={COLORS[window]}>
        {prefix}
        {window}
      </LegendItem>
    ));
  const axis = (
    <XAxis
      dataKey="trade_date"
      minTickGap={52}
      tickFormatter={(date: string) => date.slice(2).replaceAll("-", "/")}
      axisLine={false}
      tickLine={false}
      dy={8}
    />
  );
  const grid = (
    <CartesianGrid vertical={false} stroke="#edf0e8" strokeDasharray="3 4" />
  );
  const lines = (prefix: "ma" | "volume_ma" | "volatility", label: string) =>
    WINDOWS.filter((window) => windows.includes(window)).map((window) => (
      <Line
        key={window}
        dataKey={`${prefix}${window}` as keyof ChartRow}
        name={`${label}${window}`}
        stroke={COLORS[window]}
        strokeWidth={1.6}
        dot={false}
        connectNulls={false}
        isAnimationActive={false}
      />
    ));

  return (
    <div className="min-h-screen lg:flex">
      <aside className="hidden w-[224px] shrink-0 border-r border-[#dfe5dd] bg-[#edf0e8] lg:block">
        <div className="sticky top-0 flex min-h-screen flex-col px-5 py-7">
          <div className="flex items-center gap-3">
            <div className="flex size-9 items-center justify-center rounded-lg bg-[#203c32] text-white">
              <Sprout size={21} />
            </div>
            <div>
              <div className="text-sm font-semibold tracking-tight">
                Quant Forge
              </div>
              <div className="mono text-[9px] tracking-[.18em] text-muted-foreground">
                RESEARCH WORKSPACE
              </div>
            </div>
          </div>
          <div className="mt-10 flex items-center gap-2 rounded-md bg-white/80 px-3 py-2.5 text-xs font-semibold text-primary">
            <BarChart3 size={15} />
            指标研究
            <span className="ml-auto size-1.5 rounded-full bg-primary" />
          </div>
          <div className="mt-8 mb-3 flex items-center justify-between px-2 text-[10px] tracking-wider text-muted-foreground">
            <span>研究股票池</span>
            <span className="mono">
              {String(stocks.length).padStart(2, "0")}
            </span>
          </div>
          <div className="space-y-1">
            {stocks.map((stock) => (
              <button
                key={stock.symbol}
                onClick={() => setSymbol(stock.symbol)}
                className={cn(
                  "flex w-full items-center justify-between rounded-md border border-transparent px-3 py-3 text-left transition-colors hover:bg-white/60",
                  symbol === stock.symbol &&
                    "border-[#d4ded0] bg-white shadow-xs",
                )}
                aria-pressed={symbol === stock.symbol}
              >
                <div>
                  <p className="text-xs font-medium">{stock.name}</p>
                  <p className="mono mt-1 text-[10px] text-muted-foreground">
                    {stock.symbol.slice(3)} · {stock.industry}
                  </p>
                </div>
                <ChevronRight
                  size={13}
                  className={
                    symbol === stock.symbol
                      ? "text-primary"
                      : "text-muted-foreground/40"
                  }
                />
              </button>
            ))}
          </div>
          <div className="mt-auto pt-10">
            <div className="rounded-lg border border-[#dce2d6] p-3">
              <div className="flex items-center gap-2 text-[11px]">
                <Database size={12} className="text-primary" />
                本地市场数据
                <span className="ml-auto size-1.5 rounded-full bg-primary" />
              </div>
              <p className="mono mt-2 text-[9px] leading-relaxed text-muted-foreground">
                BaoStock / A-SHARES
                <br />
                日频 · {priceLabel}基准
              </p>
            </div>
            <p className="mono mt-4 text-center text-[9px] text-muted-foreground">
              QUANT FORGE / 01
            </p>
          </div>
        </div>
      </aside>
      <main className="min-w-0 flex-1">
        <header className="flex h-[70px] items-center justify-between border-b border-border px-5 sm:px-9">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Layers3 size={14} />
            <span>研究工作台</span>
            <ChevronRight size={11} />
            <span className="text-foreground">指标研究</span>
          </div>
          <div className="flex items-center gap-3">
            <Badge
              variant="outline"
              className="rounded-sm border-border font-normal text-[10px]"
            >
              A 股 · 日频
            </Badge>
            <Button
              size="icon"
              variant="ghost"
              aria-label="刷新数据"
              onClick={() => setRevision((value) => value + 1)}
            >
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            </Button>
          </div>
        </header>
        <div className="mx-auto max-w-[1440px] px-5 py-7 sm:px-9">
          <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="mono mb-2 text-[10px] tracking-[.2em] text-muted-foreground">
                MARKET OBSERVATORY
              </p>
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-semibold tracking-tight">
                  {selected?.name ?? "指标研究"}
                </h1>
                {selected && (
                  <Badge
                    variant="secondary"
                    className="rounded-sm text-[10px] font-normal"
                  >
                    {selected.industry}
                  </Badge>
                )}
              </div>
              <p className="mono mt-2 text-xs text-muted-foreground">
                {selected
                  ? `${selected.symbol.toUpperCase()}  /  ${selected.start_date} — ${selected.end_date}`
                  : "股票价格、成交量与收益表现"}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="size-1.5 rounded-full bg-primary" />
              <span className="text-[10px] text-muted-foreground">
                实时计算 · {priceLabel}
              </span>
            </div>
          </div>
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-white px-4 py-3">
            <div className="flex min-w-0 flex-wrap items-center gap-2 sm:gap-3">
              <span className="hidden text-xs text-muted-foreground sm:inline">
                股票
              </span>
              <Select
                value={symbol || undefined}
                onValueChange={setSymbol}
                disabled={listLoading}
              >
                <SelectTrigger
                  className="w-[132px] border-none sm:w-[158px] bg-secondary/60 text-xs"
                  aria-label="选择股票"
                >
                  <SelectValue placeholder="选择股票" />
                </SelectTrigger>
                <SelectContent>
                  {stocks.map((stock) => (
                    <SelectItem key={stock.symbol} value={stock.symbol}>
                      {stock.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <span className="mx-1 hidden h-5 border-l border-border sm:block" />
              <div className="flex gap-1">
                {WINDOWS.map((window) => (
                  <Button
                    key={window}
                    variant="ghost"
                    size="sm"
                    aria-pressed={windows.includes(window)}
                    onClick={() =>
                      setWindows((current) =>
                        current.includes(window)
                          ? current.filter((item) => item !== window)
                          : [...current, window],
                      )
                    }
                    className={cn(
                      "h-8 px-2.5 text-[11px]",
                      windows.includes(window) &&
                        "bg-secondary text-foreground",
                    )}
                  >
                    <span
                      className="mr-1.5 size-1.5 rounded-full"
                      style={{ background: COLORS[window] }}
                    />
                    {window} 日
                  </Button>
                ))}
              </div>
            </div>
            <div className="flex gap-0.5" aria-label="时间范围">
              {PERIODS.map((item) => (
                <Button
                  key={item.value}
                  size="sm"
                  variant={period === item.value ? "default" : "ghost"}
                  onClick={() => {
                    setPeriod(item.value);
                    setStartDate("");
                    setEndDate("");
                  }}
                  className="h-8 px-2.5 text-[11px]"
                >
                  {item.label}
                </Button>
              ))}
            </div>
          </div>
          <div className="mb-5 flex flex-wrap items-end gap-3 rounded-lg border border-border bg-white px-4 py-3">
            <label className="flex flex-col gap-1.5 text-xs text-muted-foreground">
              开始日期
              <input
                type="date"
                aria-label="开始日期"
                value={requestedStart}
                onChange={(event) => {
                  setStartDate(event.target.value);
                  setEndDate(requestedEnd);
                  setPeriod("custom");
                }}
                className="h-9 rounded-md border bg-background px-2 text-foreground"
              />
            </label>
            <label className="flex flex-col gap-1.5 text-xs text-muted-foreground">
              结束日期
              <input
                type="date"
                aria-label="结束日期"
                value={requestedEnd}
                onChange={(event) => {
                  setEndDate(event.target.value);
                  setStartDate(requestedStart);
                  setPeriod("custom");
                }}
                className="h-9 rounded-md border bg-background px-2 text-foreground"
              />
            </label>
            <div className="flex flex-col gap-1.5 text-xs text-muted-foreground">
              <span>复权方式</span>
              <Select
                value={adjustType}
                onValueChange={(value) => setAdjustType(value as "qfq" | "hfq")}
              >
                <SelectTrigger className="w-[130px]" aria-label="复权方式">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="qfq">前复权</SelectItem>
                  <SelectItem value="hfq">后复权</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button
              onClick={() => setRevision((value) => value + 1)}
              disabled={loading || !symbol}
              className="h-9"
            >
              重新计算
            </Button>
            <span className="self-center text-[10px] text-muted-foreground">
              参数变化后自动计算
            </span>
          </div>
          {error ? (
            <Card className="my-12 p-8 text-center shadow-none" role="alert">
              <Activity className="mx-auto mb-3 text-muted-foreground" />
              <h2 className="font-medium">暂时无法读取数据</h2>
              <p className="mt-2 text-sm text-muted-foreground">{error}</p>
              <Button
                className="mx-auto mt-5"
                onClick={() => setRevision((value) => value + 1)}
              >
                重新加载
              </Button>
            </Card>
          ) : loading ? (
            <div className="space-y-5" aria-label="正在加载图表">
              <Skeleton className="h-28 w-full" />
              <Skeleton className="h-[390px] w-full" />
              <Skeleton className="h-[250px] w-full" />
            </div>
          ) : latest && first ? (
            <>
              <div className="mb-7 grid grid-cols-2 gap-y-3 px-1 sm:grid-cols-4">
                <Metric
                  label={`${priceLabel}收盘价`}
                  value={`¥ ${money(latest.close)}`}
                  detail={`${latest.trade_date} · 复权价格，非实际成交价`}
                />
                <Metric
                  label="最新交易日收益"
                  value={percent(change)}
                  positive={change >= 0}
                  detail="相对上一交易记录"
                />
                <Metric
                  label="区间收益"
                  value={percent(rangeReturn)}
                  positive={rangeReturn >= 0}
                  detail={`相对 ${first.trade_date} 收盘价`}
                />
                <Metric
                  label="20 日波动率"
                  value={
                    latest.volatility20 == null
                      ? "—"
                      : `${(latest.volatility20 * 100).toFixed(2)}%`
                  }
                  detail="每日收益率标准差 · 未年化"
                />
              </div>
              <div className="space-y-5">
                <Plot
                  title="价格与均线"
                  subtitle={`${priceLabel}收盘价 · 元`}
                  height={340}
                  legend={
                    <>
                      <LegendItem color="#277562">收盘价</LegendItem>
                      {legend("MA")}
                    </>
                  }
                >
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart
                      data={data}
                      syncId="market"
                      margin={{ top: 8, right: 12, left: 4, bottom: 12 }}
                    >
                      {grid}
                      {axis}
                      <YAxis
                        width={70}
                        domain={["auto", "auto"]}
                        tickFormatter={(value: number) => number.format(value)}
                        axisLine={false}
                        tickLine={false}
                      />
                      <Tooltip content={<ChartTooltip />} />
                      <Area
                        type="linear"
                        dataKey="close"
                        name="收盘价"
                        stroke="#277562"
                        strokeWidth={2}
                        fill="#277562"
                        fillOpacity={0.055}
                        isAnimationActive={false}
                      />
                      {lines("ma", "MA")}
                    </ComposedChart>
                  </ResponsiveContainer>
                </Plot>
                <Plot
                  title="成交量与均量"
                  subtitle="原始成交量 · 股；空值保留断点"
                  height={190}
                  legend={
                    <>
                      <LegendItem color="#b9caba">成交量</LegendItem>
                      {legend("均量")}
                    </>
                  }
                >
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart
                      data={data}
                      syncId="market"
                      margin={{ top: 4, right: 12, left: 4, bottom: 12 }}
                    >
                      {grid}
                      {axis}
                      <YAxis
                        width={70}
                        tickFormatter={compactVolume}
                        axisLine={false}
                        tickLine={false}
                      />
                      <Tooltip content={<ChartTooltip unit="volume" />} />
                      <Bar
                        dataKey="volume"
                        name="成交量"
                        fill="#b9caba"
                        maxBarSize={6}
                        isAnimationActive={false}
                      />
                      {lines("volume_ma", "均量")}
                    </ComposedChart>
                  </ResponsiveContainer>
                </Plot>
                <div className="grid gap-5 xl:grid-cols-2">
                  <Plot
                    title="累计收益率"
                    subtitle={`基准：请求区间首日 ${response?.baseline_date ?? ""}`}
                    height={210}
                    legend={<LegendItem color="#277562">累计收益</LegendItem>}
                  >
                    <ResponsiveContainer width="100%" height="100%">
                      <ComposedChart
                        data={data}
                        syncId="market"
                        margin={{ top: 4, right: 12, left: 0, bottom: 12 }}
                      >
                        {grid}
                        {axis}
                        <YAxis
                          width={60}
                          tickFormatter={(value: number) =>
                            `${(value * 100).toFixed(0)}%`
                          }
                          axisLine={false}
                          tickLine={false}
                        />
                        <ReferenceLine y={0} stroke="#b9c4b7" />
                        <Tooltip content={<ChartTooltip unit="percent" />} />
                        <Area
                          dataKey="cumulative_return"
                          name="累计收益"
                          stroke="#277562"
                          fill="#277562"
                          fillOpacity={0.07}
                          strokeWidth={1.8}
                          isAnimationActive={false}
                        />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </Plot>
                  <Plot
                    title="收益率波动率"
                    subtitle="每日收益率样本标准差 · 未年化"
                    height={210}
                    legend={legend("波动率")}
                  >
                    <ResponsiveContainer width="100%" height="100%">
                      <ComposedChart
                        data={data}
                        syncId="market"
                        margin={{ top: 4, right: 12, left: 0, bottom: 12 }}
                      >
                        {grid}
                        {axis}
                        <YAxis
                          width={60}
                          tickFormatter={(value: number) =>
                            `${(value * 100).toFixed(1)}%`
                          }
                          axisLine={false}
                          tickLine={false}
                        />
                        <Tooltip content={<ChartTooltip unit="percent" />} />
                        {lines("volatility", "波动率")}
                      </ComposedChart>
                    </ResponsiveContainer>
                  </Plot>
                </div>
              </div>
              <footer className="mt-5 flex flex-wrap justify-between gap-2 text-[10px] text-muted-foreground">
                <span className="flex items-center gap-1.5">
                  {change >= 0 ? (
                    <ArrowUpRight size={12} />
                  ) : (
                    <ArrowDownRight size={12} />
                  )}
                  窗口不足保留空值 · 图表悬停联动
                </span>
                <span className="mono">
                  {first.trade_date} — {latest.trade_date} /{" "}
                  {data.length.toLocaleString()} 条交易记录
                </span>
              </footer>
            </>
          ) : (
            <Card className="p-8 text-center text-sm text-muted-foreground shadow-none">
              所选股票暂无可显示的数据。
            </Card>
          )}
        </div>
      </main>
    </div>
  );
}
