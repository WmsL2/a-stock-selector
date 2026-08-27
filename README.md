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
