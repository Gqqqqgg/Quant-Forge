import { parseDefinition, type StrategyDefinition } from "@/lib/strategy";

export type ParameterValue = string | number | null;
export type ParameterSchema = {
  title: string; type?: string; format?: string; enum?: (string | null)[];
  minimum?: number; maximum?: number; anyOf?: ParameterSchema[];
};
export type Strategy = {
  id: string; description: string; definition: StrategyDefinition;
  universe: { symbol: string; name: string; industry: string }[];
  parameters: Record<string, ParameterValue>;
  parameter_schema: { properties: Record<string, ParameterSchema> };
};

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options);
  if (!response.headers.get("content-type")?.includes("application/json")) {
    throw new Error("无法连接策略服务，请确认后端已启动。");
  }
  const value = await response.json();
  if (!response.ok) {
    const detail = typeof value.detail === "string" ? value.detail : Array.isArray(value.detail)
      ? value.detail.map((item: { loc?: (string | number)[]; msg?: string }) => `${item.loc?.slice(1).join(".") ?? "参数"}：${item.msg ?? "格式无效"}`).join("\n") : undefined;
    throw new Error(value.error ?? detail ?? "请求失败，请稍后重试。");
  }
  return value as T;
}

export function validateStrategy(value: Strategy): Strategy {
  parseDefinition(value.definition);
  if (!value.id || !value.parameters || !value.parameter_schema?.properties || !Array.isArray(value.universe)) {
    throw new Error("策略展示数据不完整。");
  }
  return value;
}

export const FACTOR_INFO: Record<string, { description: string; formula: string; note: string }> = {
  range_return: { description: "观察所选区间内的价格变化。", formula: "末日收盘价 / 首日收盘价 − 1", note: "使用复权价格，首日作为区间基准。" },
  max_drawdown: { description: "衡量区间内从价格峰值到后续低点的最大跌幅。", formula: "max(1 − 收盘价 / 截至当日最高收盘价)", note: "返回非负比例，只计算所选区间。" },
  volatility: { description: "衡量区间内日收益的波动程度。", formula: "区间日收益率的样本标准差", note: "不年化；不包含首日相对区间前一天的收益，样本不足时为空。" },
  ma20_deviation: { description: "观察价格相对短期均线的位置。", formula: "末日收盘价 / MA20 − 1", note: "使用截至结束日的历史数据预热，20 条价格数据不足时为空。" },
  ma60_deviation: { description: "观察价格相对中期均线的位置。", formula: "末日收盘价 / MA60 − 1", note: "使用截至结束日的历史数据预热，60 条价格数据不足时为空。" },
  volume_ratio: { description: "比较末日成交量与近期平均成交量。", formula: "末日成交量 / 20 日平均成交量", note: "以倍数表示；均量不足或为零时为空。" },
  excess_return: { description: "比较股票与所选基准的区间表现。", formula: "股票区间收益 − 基准区间收益", note: "以百分点表示；基准必须覆盖股票实际区间的起止日。" },
};
