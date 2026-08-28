# A Stock Selector

这是一个个人使用的 A 股量化研究与实时选股系统。

## 规划方向

- 覆盖全部 A 股
- 沪深主板
- 创业板
- 科创板
- 北交所可配置
- 多因子量化选股
- 日频基础评分
- 盘中实时评分
- 可解释的入选原因
- 风险标签
- 历史回测
- 防未来函数
- 防幸存者偏差
- 次新股不因上市时间不足而直接排除

当前项目仅完成工程初始化，以上业务功能尚未实现。

## 风险声明

本项目仅用于个人投资研究和技术研究，不构成任何投资建议，也不保证任何投资收益。

## 开发命令

```powershell
python -m pip install -e ".[dev]"
python -m stock_selector --help
python -m stock_selector version
pytest
ruff check .
mypy src
```

## 配置

工程基础配置位于 `config/default.yaml`、`config/markets.yaml` 和
`config/factors.yaml`。可使用以下命令检查配置及项目路径：

```powershell
python -m stock_selector config check
python -m stock_selector config paths
```

项目仍处于工程基础阶段，尚未实现任何金融数据或选股功能。

目前已完成工程骨架、配置与日志、核心领域数据模型、Provider 抽象、AKShare 基础 Provider，
以及轻量本地存储层。当前仅接入 Instrument、DailyBar 与 RealtimeQuote；尚未完成股票池、
因子、实时评分、前端和回测。
实时行情优先使用 Eastmoney；仅当其连接不可用时回退到 Sina。两者均为免费上游，
可能受到网络波动、限流或服务端变更影响。

## Storage strategy

采用“全市场轻量元数据 + 选择性详细持久化”：Instrument master 可保存全市场；DailyBar
只保存调用者明确指定的 symbol；RealtimeQuote 只保存调用者明确选择的快照。Parquet 是数据
源，DuckDB 仅通过外部 view 查询 Parquet，不复制一份数据。未来由 BaseScore / candidate pool
决定详细持久化覆盖范围；当前未实现候选池选择。

长期方向是 Task 08 保存全市场有限滚动日线窗口、Task 16 仅为候选/关注层保存分钟线、Task 25
执行 retention cleanup；Task 23 的大型历史回测数据将显式构建，而不会要求日常运行无限保留历史。

```powershell
python -m stock_selector data instruments-once
python -m stock_selector data realtime-once
python -m stock_selector data daily-once 600519.SH --start 2026-08-03 --end 2026-08-07
python -m stock_selector storage status
python -m stock_selector storage smoke 600519.SH --start 2026-08-03 --end 2026-08-07
```
