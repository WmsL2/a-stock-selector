# A-Share Stock Selector

个人、本地运行的 A 股量化选股与选股研究平台，面向研究和技术学习，不构成投资建议。它将本地证据、可解释候选选股和持久化研究快照连接为可复现的研究流程，而不是交易或资产管理产品。

## Current capabilities

- 本地结构化股票池、风险状态与就绪度证据；财务、估值、行业和 PIT 安全的复权收益证据。
- 因子预处理、五因子族、BaseScore 与确定性可解释性；日选股和实时候选/选股工作流。
- 有界、手动的数据刷新工具；不会在启动或读取页面时自动进行全市场下载。
- 持久化选股研究快照、前瞻收益标签、有效性分析（精确排名与排名阈值）、历史、稳定性、筛选、比较和导出。
- 已加固的请求状态：较新的请求优先，失败或重叠请求期间仍保留上一次成功结果。

这些能力仅描述研究证据和选股结果，不表示买卖建议或自动交易决策。

## Architecture

```text
Vue frontend
  -> local HTTP API
  -> FastAPI / quant core
  -> repository
  -> local runtime storage
```

- `frontend/`：Vue、TypeScript 与 Vite 前端。
- `backend/`：FastAPI、量化核心、CLI、provider 与仓储。
- `runtime/`：本地生成的 Parquet、DuckDB、日志和研究快照。
- `docs/`：架构、运行和验收文档。
- `scripts/`：PowerShell 开发与验证入口。

## Prerequisites

仓库脚本按 Windows / PowerShell 工作流验证。需要 Python 3.12、仓库根目录的 `.venv`，以及前端所需的 Node/npm。仓库未声明固定 Node 版本。

## Installation

在仓库根目录安装后端：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".\backend[dev]"
```

安装前端依赖：

```powershell
Push-Location frontend
npm install
Pop-Location
```

## Running locally

从仓库根目录启动后端、前端或两者：

```powershell
.\scripts\start-backend.ps1
.\scripts\start-frontend.ps1
.\scripts\start-dev.ps1
```

后端地址为 <http://127.0.0.1:8000>，健康检查为 <http://127.0.0.1:8000/api/health>。前端使用 Vite；请使用 Vite 输出的 URL，而不是假定固定端口。

## Validation

完整本地验证入口：

```powershell
.\scripts\test-all.ps1
```

它运行后端 pytest 与覆盖率、Ruff、mypy，以及前端 type-check、ESLint、Vitest 和生产构建。Task59/Task60 基线结果为：后端 1048 passed、覆盖率 91%、mypy 123 个源文件；前端 16 个文件 / 99 条测试、构建 PASS。这些是当前基线，不是未来变更的永久保证。

## Runtime state

生成数据保留在 `runtime/`，且有意不提交。不要提交 Parquet、DuckDB、生成日志、凭据、令牌或生成的研究/运行时产物。删除运行时数据不等同于卸载源码，可能移除已收集的证据和研究快照。

## Product boundary

本项目不包含买卖建议、持仓、仓位大小、资金管理、组合构建或优化、再平衡逻辑、交易成本/滑点模拟、NAV/PnL、组合层回测、券商集成或自动/实盘交易。

## Documentation

- [本地部署与运行](docs/deployment.md)
- [最终验收](docs/acceptance.md)
- [实现状态](docs/implementation_status.md)
- [仓库布局](docs/architecture/repository-layout.md)
