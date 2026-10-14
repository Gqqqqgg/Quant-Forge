export const METRICS = [
  { key: "range_return", label: "区间收益", scale: 100, unit: "%" },
  { key: "max_drawdown", label: "最大回撤", scale: 100, unit: "%" },
  { key: "volatility", label: "区间日收益波动率", scale: 100, unit: "%" },
  { key: "ma20_deviation", label: "价格相对 MA20", scale: 100, unit: "%" },
  { key: "ma60_deviation", label: "价格相对 MA60", scale: 100, unit: "%" },
  { key: "volume_ratio", label: "末日成交量 / 20 日均量", scale: 1, unit: "倍" },
  { key: "excess_return", label: "跑赢基准", scale: 100, unit: "百分点" },
] as const;
export type Metric = typeof METRICS[number]["key"];
export type Condition = { metric: Metric; operator: "gte" | "lte"; value: number };
export type StrategyDefinition = {
  name: string; source: "baostock" | "tushare"; start_date: string; end_date: string;
  adjust_type: "none" | "qfq" | "hfq"; benchmark_symbol: string | null;
  conditions: Condition[]; sort_by: Metric; sort_direction: "asc" | "desc";
};
export type Candidate = {
  symbol: string; name: string; industry: string; start_date: string; end_date: string; rows: number;
  metrics: Record<Metric, number | null>;
  checks: (Condition & { actual: number | null; passed: boolean })[];
  comparison_error: string | null;
};
export type StrategyResult = {
  definition: StrategyDefinition; total: number; matched: number;
  candidates: Candidate[]; excluded: Candidate[];
  errors: { symbol: string; name: string; error: string }[];
};
export const EXAMPLE: StrategyDefinition = {
  name: "趋势与回撤筛选示例", source: "baostock", start_date: "2026-07-13", end_date: "2026-10-13",
  adjust_type: "hfq", benchmark_symbol: "sh.000300",
  conditions: [{ metric: "ma20_deviation", operator: "gte", value: 0 }, { metric: "max_drawdown", operator: "lte", value: 0.15 }],
  sort_by: "range_return", sort_direction: "desc",
};
export function metricText(key: Metric, value: number | null) {
  const metric = METRICS.find((item) => item.key === key)!;
  return value == null ? "数据不足" : `${(value * metric.scale).toFixed(2)} ${metric.unit}`;
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function numeric(value: unknown): value is number { return typeof value === "number" && Number.isFinite(value); }
function validDate(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}
function metric(value: unknown): value is Metric { return METRICS.some((item) => item.key === value); }
function condition(value: unknown): value is Condition {
  return record(value) && metric(value.metric) && ["gte", "lte"].includes(String(value.operator)) && numeric(value.value);
}
export function parseDefinition(value: unknown): StrategyDefinition {
  if (!record(value) || typeof value.name !== "string" || !value.name.trim()
    || !["baostock", "tushare"].includes(String(value.source)) || !validDate(value.start_date) || !validDate(value.end_date)
    || value.start_date > value.end_date || !["none", "qfq", "hfq"].includes(String(value.adjust_type))
    || (value.benchmark_symbol !== null && (typeof value.benchmark_symbol !== "string" || !/^(sh|sz|bj)\.\d{6}$/.test(value.benchmark_symbol)))
    || !Array.isArray(value.conditions) || value.conditions.length > 20 || !value.conditions.every(condition)
    || !metric(value.sort_by) || !["asc", "desc"].includes(String(value.sort_direction))) {
    throw new Error("策略定义格式无效，请检查名称、日期和筛选条件。");
  }
  if (value.benchmark_symbol === null && (value.sort_by === "excess_return" || value.conditions.some((item) => item.metric === "excess_return"))) {
    throw new Error("超额收益筛选或排序需要选择基准。");
  }
  return value as StrategyDefinition;
}
function candidate(value: unknown): value is Candidate {
  return record(value) && ["symbol", "name", "industry"].every((key) => typeof value[key] === "string")
    && validDate(value.start_date) && validDate(value.end_date) && value.start_date <= value.end_date
    && Number.isInteger(value.rows) && Number(value.rows) > 0 && record(value.metrics)
    && METRICS.every((item) => value.metrics && record(value.metrics) && (value.metrics[item.key] === null || numeric(value.metrics[item.key])))
    && Array.isArray(value.checks) && value.checks.every((check) => record(check) && (check.actual === null || numeric(check.actual)) && typeof check.passed === "boolean" && condition(check))
    && (value.comparison_error === null || typeof value.comparison_error === "string");
}
export function parseResult(value: unknown): StrategyResult {
  if (!record(value)) throw new Error("结果必须是 JSON 对象。");
  parseDefinition(value.definition);
  if (!Number.isInteger(value.total) || Number(value.total) < 0 || !Number.isInteger(value.matched)
    || !Array.isArray(value.candidates) || !value.candidates.every(candidate)
    || !Array.isArray(value.excluded) || !value.excluded.every(candidate)
    || !Array.isArray(value.errors) || !value.errors.every((error) => record(error) && ["symbol", "name", "error"].every((key) => typeof error[key] === "string"))
    || value.matched !== value.candidates.length || value.total !== value.candidates.length + value.excluded.length + value.errors.length) {
    throw new Error("运行结果格式无效，请导入后端 main.py 输出的结果 JSON。");
  }
  return value as StrategyResult;
}
export function downloadJson(name: string, value: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
  const link = document.createElement("a"); link.href = url; link.download = name; link.click();
  URL.revokeObjectURL(url);
}
