# TimesFM Phase 2 实施计划 — 高级预测功能

> **执行方式:** 使用 superpowers:subagent-driven-development 按任务分发子代理执行

**目标:** 在 Phase 1 核心集成基础上，实现 5 项高级预测功能

**前置条件:** Phase 1 已全部完成（commit 44e3c74）

---

## 文件结构

### 新建文件
```
src/services/forecast_chart_service.py    # 预测图表生成
src/services/forecast_accuracy_service.py # 准确率追踪服务
src/services/forecast_covariate_builder.py # 协变量构建器
src/services/forecast_ensemble_service.py  # 多模型集成
src/repositories/forecast_repo.py         # 预测数据持久化
src/schemas/forecast_chart_schema.py      # 图表数据 Schema
src/schemas/forecast_accuracy_schema.py   # 准确率 Schema
api/v1/endpoints/forecast.py             # 预测 API 端点
tests/test_forecast_chart_service.py     # 图表测试
tests/test_forecast_accuracy_service.py  # 准确率测试
tests/test_forecast_covariate_builder.py # 协变量测试
tests/test_forecast_ensemble_service.py  # 集成测试
tests/test_forecast_repo.py              # 持久化测试
```

### 修改文件
```
src/storage.py                            # 新增预测相关表
src/services/timesfm_service.py           # 支持协变量和模型注册
src/services/analysis_service.py          # 增强 forecast 集成
src/core/config_registry.py              # 新增 Phase 2 配置
src/core/pipeline.py                     # 存储预测结果和实时更新
.env.example                             # 新增环境变量
requirements.txt                         # 新增 matplotlib
api/v1/router.py                         # 注册 forecast 路由
docs/CHANGELOG.md                        # 更新日志
```

---

## Task 1: 预测图表生成

**目标:** 使用 matplotlib 生成预测图表（历史价格 + 预测曲线 + 置信区间）

### 1.1 添加 matplotlib 依赖

在 `requirements.txt` 末尾添加：
```txt
matplotlib>=3.7.0
```

### 1.2 创建图表 Schema

创建 `src/schemas/forecast_chart_schema.py`:
```python
@dataclass
class ForecastChartConfig:
    """图表配置"""
    width: int = 12         # 图表宽度（英寸）
    height: int = 6         # 图表高度（英寸）
    dpi: int = 150          # 分辨率
    show_confidence: bool = True  # 显示置信区间
    confidence_level: float = 0.8 # 置信水平
    show_history_days: int = 90   # 显示历史天数
    format: str = "png"     # 输出格式 png/svg
    style: str = "seaborn-v0_8-whitegrid"  # 样式

@dataclass
class ForecastChartData:
    """图表数据"""
    chart_base64: str       # Base64 编码的图片
    chart_path: Optional[str]  # 图片文件路径
    width: int
    height: int
```

### 1.3 创建图表生成服务

创建 `src/services/forecast_chart_service.py`:
- `generate_forecast_chart()` — 生成单股预测图表
- `generate_comparison_chart()` — 生成多模型对比图表
- `_plot_history()` — 绘制历史价格区域
- `_plot_forecast()` — 绘制预测曲线
- `_plot_confidence_band()` — 绘制置信区间带
- `chart_to_base64()` — 图表转 Base64

核心逻辑：
1. 使用 matplotlib 的 fill_between 绘制置信区间
2. 历史价格用实线，预测用虚线
3. 分界线标注"今天"
4. 输出 Base64 图片字符串用于报告嵌入

### 1.4 集成到报告模板

修改 `templates/forecast_section.zh.jinja2` 和 `templates/forecast_section.en.jinja2`：
- 在预测概要后添加图表展示区域
- 使用 Base64 图片嵌入 Markdown（`![forecast](data:image/png;base64,...)`）

### 1.5 集成到 analysis_service

在 `_run_timesfm_forecast` 返回结果中添加 `chart_base64` 字段。

### 1.6 测试

创建 `tests/test_forecast_chart_service.py`:
- 测试图表生成（使用 mock 数据）
- 测试 Base64 输出格式
- 测试不同配置组合

---

## Task 2: 历史准确率追踪

**目标:** 持久化预测记录，定期对比实际价格，计算准确率指标

### 2.1 新增数据库表

在 `src/storage.py` 新增：

```python
class ForecastRecord(Base):
    """预测记录表"""
    __tablename__ = "forecast_records"
    id: int (PK)
    query_id: str          # 关联分析记录
    stock_code: str        # 股票代码
    stock_name: str        # 股票名称
    prediction_date: datetime  # 预测日期
    current_price: float   # 预测时价格
    point_forecast: str    # JSON: 预测值数组
    quantile_forecast: str # JSON: 分位数预测
    horizon: int           # 预测天数
    context_length: int    # 上下文长度
    model_version: str     # 模型版本
    trend_direction: str   # 趋势方向
    evaluated: bool        # 是否已评估
    created_at: datetime   # 创建时间

class ForecastEvaluation(Base):
    """预测评估表"""
    __tablename__ = "forecast_evaluations"
    id: int (PK)
    forecast_record_id: int (FK -> forecast_records.id)
    actual_prices: str     # JSON: 实际价格数组
    mae: float             # 平均绝对误差
    mape: float            # 平均绝对百分比误差
    rmse: float            # 均方根误差
    direction_correct: bool  # 方向是否正确
    evaluated_at: datetime  # 评估时间
```

### 2.2 创建持久化仓库

创建 `src/repositories/forecast_repo.py`:
- `save_forecast()` — 存储预测记录
- `get_pending_evaluations()` — 获取待评估的预测
- `save_evaluation()` — 存储评估结果
- `get_accuracy_summary()` — 获取准确率汇总
- `get_stock_accuracy()` — 获取单股准确率

### 2.3 创建准确率服务

创建 `src/services/forecast_accuracy_service.py`:
- `record_forecast()` — 记录预测结果
- `evaluate_forecast()` — 评估单条预测（对比实际价格）
- `evaluate_pending()` — 批量评估待处理预测
- `get_accuracy_report()` — 生成准确率报告
- `_calculate_metrics()` — 计算 MAE/MAPE/RMSE

核心逻辑：
1. 每次预测后自动存储到 forecast_records 表
2. 定时任务（复用回测框架）检查已到期的预测（actual_days >= horizon）
3. 从 data_provider 获取实际价格，与预测对比
4. 计算各项指标并写入 forecast_evaluations 表

### 2.4 集成到 pipeline

在 `src/core/pipeline.py` 的 `process_single_stock` 中：
- 预测成功后调用 `forecast_accuracy_service.record_forecast()`
- 非侵入式：记录失败不影响主流程

### 2.5 新增 API 端点

创建 `api/v1/endpoints/forecast.py`:
- `GET /api/v1/forecast/accuracy` — 获取总体准确率
- `GET /api/v1/forecast/accuracy/{stock_code}` — 获取单股准确率
- `POST /api/v1/forecast/evaluate` — 触发批量评估
- `GET /api/v1/forecast/records` — 获取预测记录列表

在 `api/v1/router.py` 注册新路由。

### 2.6 测试

创建 `tests/test_forecast_accuracy_service.py` 和 `tests/test_forecast_repo.py`。

---

## Task 3: 协变量支持 (XReg)

**目标:** 结合成交量、技术指标等外部变量提升预测精度

### 3.1 更新 TimesFM 服务支持协变量

修改 `src/services/timesfm_service.py`:
- 新增 `predict_with_covariates()` 方法
- 支持传入额外的动态特征（dynamical covariates）
- TimesFM 2.5 支持 xreg 参数

### 3.2 创建协变量构建器

创建 `src/services/forecast_covariate_builder.py`:
- `build_covariates()` — 构建协变量矩阵
- 支持的协变量：
  - 成交量变化率
  - MA5/MA10/MA20 偏离度
  - RSI 指标
  - 布林带位置
- `validate_covariates()` — 验证协变量数据质量
- `normalize_covariates()` — 标准化

### 3.3 新增配置项

在 `config_registry.py` 添加：
```python
TIMESFM_COVARIATES_ENABLED: bool = False  # 启用协变量
TIMESFM_COVARIATE_FEATURES: str = "volume_change,ma_deviation"  # 使用的特征
```

### 3.4 集成到 analysis_service

在 `_run_timesfm_forecast` 中：
- 当 `TIMESFM_COVARIATES_ENABLED=True` 时，先构建协变量
- 调用 `predict_with_covariates()` 替代 `predict()`

### 3.5 测试

创建 `tests/test_forecast_covariate_builder.py`。

---

## Task 4: 多模型集成

**目标:** 集成多个时间序列模型，融合预测提高鲁棒性

### 4.1 创建模型注册表

在 `src/services/timesfm_service.py` 或新建 `src/services/forecast_ensemble_service.py`:
```python
class ForecastModelRegistry:
    """预测模型注册表"""
    _models: Dict[str, Type[ForecastModel]] = {}

    @classmethod
    def register(cls, name: str, model_cls: Type[ForecastModel]):
        cls._models[name] = model_cls

    @classmethod
    def get(cls, name: str) -> Type[ForecastModel]:
        return cls._models[name]

class ForecastModel(ABC):
    """预测模型基类"""
    @abstractmethod
    def predict(self, data: np.ndarray, horizon: int) -> Dict[str, Any]:
        pass

class TimesFMModel(ForecastModel):
    """TimesFM 模型适配器"""

class NaiveSeasonalModel(ForecastModel):
    """朴素季节模型（统计基线）"""

class MovingAverageModel(ForecastModel):
    """移动平均模型（统计基线）"""
```

### 4.2 创建集成服务

创建 `src/services/forecast_ensemble_service.py`:
- `predict_ensemble()` — 多模型集成预测
- 支持的集成策略：
  - 简单平均（Simple Average）
  - 加权平均（Weighted Average，基于历史准确率加权）
  - 中位数集成（Median Ensemble）
- `_combine_predictions()` — 合并多个模型预测
- `_calculate_weights()` — 基于历史准确率计算权重

### 4.3 新增配置项

```python
TIMESFM_ENSEMBLE_ENABLED: bool = False
TIMESFM_ENSEMBLE_MODELS: str = "timesfm,naive_seasonal,moving_average"
TIMESFM_ENSEMBLE_STRATEGY: str = "weighted_average"  # simple/weighted/median
```

### 4.4 集成到 analysis_service

当 `TIMESFM_ENSEMBLE_ENABLED=True` 时使用集成预测。

### 4.5 测试

创建 `tests/test_forecast_ensemble_service.py`。

---

## Task 5: 实时预测更新

**目标:** 盘中实时更新预测结果

### 5.1 创建预测更新服务

创建预测缓存和更新机制（在 `forecast_accuracy_service.py` 或独立模块）：
- `update_forecast_if_stale()` — 检查预测是否过期，过期则重新预测
- `_is_stale()` — 判断预测是否过期（基于配置的刷新间隔）
- `get_cached_forecast()` — 获取缓存的预测结果
- `invalidate_cache()` — 使缓存失效

### 5.2 新增配置项

```python
TIMESFM_REALTIME_UPDATE_ENABLED: bool = False
TIMESFM_CACHE_TTL_MINUTES: int = 60  # 预测缓存有效期（分钟）
TIMESFM_UPDATE_ON_PRICE_CHANGE_PCT: float = 2.0  # 价格变化超过此值时更新
```

### 5.3 集成到 pipeline

在 `process_single_stock` 中：
- 获取实时价格后，检查预测缓存
- 如果缓存过期或价格变化超阈值，触发更新

### 5.4 新增 API 端点

在 `api/v1/endpoints/forecast.py` 添加：
- `GET /api/v1/forecast/live/{stock_code}` — 获取实时预测
- `POST /api/v1/forecast/refresh/{stock_code}` — 强制刷新预测

### 5.5 测试

在 `tests/test_forecast_accuracy_service.py` 中添加实时更新相关测试。

---

## Task 6: 更新文档和配置

**目标:** 更新 .env.example、config_registry、CHANGELOG、README

### 6.1 更新 .env.example

添加 Phase 2 所有新配置项。

### 6.2 更新 config_registry.py

添加 Phase 2 配置字段到 `_FIELD_DEFINITIONS`，类别 `ai_forecast`。

### 6.3 更新 CHANGELOG.md

在 `[Unreleased]` 添加 Phase 2 功能记录。

### 6.4 更新 README.md

更新 AI 预测章节，说明 Phase 2 新功能。

---

## Task 7: 端到端验证

### 7.1 运行所有新增测试

```bash
pytest tests/test_forecast_*.py -v
```

### 7.2 运行 CI 检查

```bash
./scripts/ci_gate.sh
```

### 7.3 手动验证

- 启用 TimesFM，运行单股分析，确认图表出现在报告中
- 检查预测记录已写入数据库
- 运行准确率评估，确认指标计算正确

---

## 执行顺序

```
Task 1 (图表) ─────────────────────────────────────┐
Task 2 (准确率追踪) ────────────────────────────────┤
Task 3 (协变量) ────────────────────────────────────┤──> Task 6 (文档) ──> Task 7 (验证)
Task 4 (多模型集成) ────────────────────────────────┤
Task 5 (实时更新) ──────────────────────────────────┘
```

Task 1-5 互相独立，可以串行执行（避免文件冲突）。Task 6 依赖 Task 1-5 完成。
