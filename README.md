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

目前已完成工程骨架、配置与日志、核心领域数据模型、Provider 抽象和 AKShare 基础 Provider。
当前仅接入 Instrument、DailyBar 与 RealtimeQuote；尚未完成存储、股票池、因子、实时评分、前端和回测。

```powershell
python -m stock_selector data instruments-once
python -m stock_selector data realtime-once
python -m stock_selector data daily-once 600519.SH --start 2026-08-03 --end 2026-08-07
```
