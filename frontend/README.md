# 指标研究前端

React + TypeScript + Vite + shadcn/ui + Tailwind CSS，使用 Recharts 展示真实本地计算数据。shadcn 组件源码位于 `src/components/ui/`，配置见 `components.json`。

UI 组件取自 shadcn 官方 `new-york-v4` 注册表，`cn` 导入映射到本地工具，Radix 导入映射到对应的 `@radix-ui/react-*` 包。

## 启动

先在仓库根目录启动后端：

```powershell
.\scripts\dev.ps1
```

在另一个终端进入 `frontend/`：

```powershell
npm install
npm run dev
```

浏览器访问 `http://127.0.0.1:5173`。Vite 将 `/api` 请求代理到 `http://127.0.0.1:8000`。后端通过 `A_STOCK_DATA_ROOT` 或默认用户数据目录读取原始 K 线与因子，按前端入参实时计算，结果不落盘。

## 图表

- 五只股票可切换，默认贵州茅台、最近一年；支持近 3 月、6 月、1 年、3 年和完整历史。
- 支持填入开始日期、结束日期，切换前复权／后复权；参数变化后自动请求计算接口，也可点击重新计算。
- 股票、日期、复权方式及选中的 5／20／60 日窗口作为 JSON 入参提交到 `POST /api/calculated/charts`，返回结果直接渲染。
- 价格与 MA5、MA20、MA60 使用同一复权基准。
- 原始成交量与 5、20、60 日平均成交量。
- 累计收益率和顶部区间收益均以请求区间首日收盘价为基准。
- 5、20、60 日收益率样本标准差，不做年化。
- 5／20／60 日开关同时控制三个图表的对应指标，悬停显示数值并联动日期。
- 缺失数据和窗口不足保留断点；加载、空数据和错误状态明确显示。

## 验证

```powershell
npm run build
```

