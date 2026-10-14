export type Stock = {
  symbol: string;
  name: string;
  industry: string;
  rows: number;
  start_date: string;
  end_date: string;
};

export type ChartRow = {
  code: string;
  trade_date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
  daily_return: number | null;
  cumulative_return: number;
  ma5?: number | null;
  ma20?: number | null;
  ma60?: number | null;
  volume_ma5?: number | null;
  volume_ma20?: number | null;
  volume_ma60?: number | null;
  volatility5?: number | null;
  volatility20?: number | null;
  volatility60?: number | null;
};

export type ChartResponse = {
  symbol: string;
  name: string;
  industry: string;
  source: string;
  adjust_type: "none" | "qfq" | "hfq";
  baseline_date: string;
  rows: number;
  data: ChartRow[];
};

export async function getJson<T>(
  path: string,
  signal: AbortSignal,
): Promise<T> {
  const response = await fetch(path, { signal });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? "数据读取失败，请确认后端服务已启动。");
  }
  return response.json() as Promise<T>;
}

export type FactorEngineParams = {
  source: "baostock" | "tushare";
  symbol: string;
  start_date: string;
  end_date: string;
  adjust_type: "none" | "qfq" | "hfq";
  windows: number[];
};

export async function getFactorEngineCharts(
  params: FactorEngineParams,
  signal: AbortSignal,
): Promise<ChartResponse> {
  const response = await fetch("/api/factor_engine/charts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
    signal,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string"
        ? body.detail
        : "计算参数无效或数据读取失败。",
    );
  }
  return response.json() as Promise<ChartResponse>;
}
