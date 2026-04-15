# TimesFM 股价预测集成设计文档

**项目**: daily_stock_analysis
**功能**: 集成 Google TimesFM 模型实现未来 60 天股价预测
**作者**: AI Assistant
**日期**: 2026-04-15
**状态**: 设计阶段

---

## 1. 概述

### 1.1 目标

在现有股票分析系统中集成 Google TimesFM（Time Series Foundation Model），提供未来 60 天的股价预测作为辅助决策参考。

### 1.2 核心原则

1. **非侵入式**: 预测功能失败不应影响主分析流程
2. **资源可控**: 支持懒加载、内存管理、可配置禁用
3. **用户友好**: 简洁摘要 + 可选详细信息
4. **合规安全**: 明确标注预测仅供参考，不构成投资建议

### 1.3 TimesFM 简介

- **开发者**: Google Research
- **类型**: 零样本时间序列预测模型
- **版本**: TimesFM 2.5 (200M 参数)
- **能力**:
  - 最大上下文: 16,384 个时间点
  - 最大预测步长: 1,000 步
  - 输出: 点预测 + 分位数预测 (10%-90%)
- **模型大小**: ~800MB
- **后端**: PyTorch (推荐) / JAX-Flax

---

## 2. 功能需求

### 2.1 使用场景

**辅助决策参考模式**:
- 在现有分析报告中增加"AI 预测"章节
- 提供参考性预测，不作为主要决策依据
- 与技术分析、基本面分析形成互补

### 2.2 输入数据

**自适应上下文模式**:
- 根据股票上市时间和数据可用性动态调整
- 优先使用最多可用数据（上限 1024 个交易日）
- 数据来源: 现有 data_provider 体系

### 2.3 输出内容

**灵活组合模式**:
- **简洁摘要**: 预测趋势、关键价格点位
- **详细数据**: 完整预测数据表格和分位数信息
- **图表展示**: 预测曲线图（历史+预测+置信区间）

### 2.4 功能控制

**分层控制模式**:
- 环境变量控制默认行为
- Web 设置页允许用户覆盖
- 支持按股票/报告类型差异化配置

---

## 3. 架构设计

### 3.1 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    Stock Analysis Pipeline               │
│                  (src/core/pipeline.py)                  │
└────────────────────┬────────────────────────────────────┘
                     │
                     ├──> Technical Analysis (现有)
                     ├──> Fundamental Analysis (现有)
                     ├──> News Analysis (现有)
                     │
                     └──> TimesFM Prediction (新增)
                          │
                          ▼
                 ┌──────────────────────┐
                 │  TimesFMService      │
                 │  (新增模块)           │
                 └──────────┬───────────┘
                            │
                            ├──> Model Loader
                            ├──> Data Preprocessor
                            ├──> Forecast Executor
                            └──> Result Postprocessor
```

### 3.2 核心组件

#### 3.2.1 TimesFMService (`src/services/timesfm_service.py`)

**职责**:
- 懒加载和管理 TimesFM 模型
- 提供统一的预测接口
- 处理数据预处理和结果后处理
- 缓存管理

**核心方法**:
```python
class TimesFMService:
    def __init__(self, config: ForecastConfig):
        """初始化服务（懒加载模型）"""

    def load_model(self) -> None:
        """加载 TimesFM 模型到内存"""

    def predict(
        self,
        prices: np.ndarray,
        horizon: int = 60,
        context_length: Optional[int] = None
    ) -> ForecastResult:
        """
        执行预测

        Args:
            prices: 历史价格序列
            horizon: 预测天数
            context_length: 上下文长度（None = 自适应）

        Returns:
            ForecastResult 对象
        """

    def is_available(self) -> bool:
        """检查服务是否可用"""

    def unload_model(self) -> None:
        """卸载模型释放内存"""
```

#### 3.2.2 ForecastResult (`src/schemas/forecast_schema.py`)

**数据结构**:
```python
@dataclass
class ForecastResult:
    """预测结果"""
    stock_code: str
    stock_name: str
    current_price: float
    prediction_date: datetime

    # 预测数据
    point_forecast: np.ndarray  # shape: (horizon,)
    quantile_forecast: np.ndarray  # shape: (horizon, 10)

    # 统计信息
    min_predicted: float
    max_predicted: float
    median_predicted: float
    trend_direction: str  # "up" / "down" / "sideways"

    # 元数据
    context_length: int
    horizon: int
    model_version: str
    generated_at: datetime

    def get_confidence_interval(self, confidence: float = 0.8) -> tuple:
        """获取指定置信区间"""

    def to_dict(self) -> dict:
        """转换为字典格式"""
```

#### 3.2.3 配置管理 (`src/core/config_registry.py`)

**新增配置字段**:
```python
# TimesFM 预测配置
TIMESFM_ENABLED: bool = False  # 全局开关
TIMESFM_MODEL_ID: str = "google/timesfm-2.5-200m-pytorch"
TIMESFM_MAX_CONTEXT: int = 0  # 0 = 自适应
TIMESFM_MAX_HORIZON: int = 60  # 最大预测天数
TIMESFM_CACHE_DIR: Optional[str] = None  # 模型缓存目录
TIMESFM_DEVICE: str = "auto"  # auto/cpu/cuda
TIMESFM_USE_QUANTILE_HEAD: bool = True  # 使用连续分位数头
```

### 3.3 数据流

```
1. 数据获取
   ├─ StockAnalysisPipeline.request_stock_data()
   └─ data_provider/ 提供历史价格数据

2. 数据预处理
   ├─ 提取收盘价序列
   ├─ 处理缺失值（线性插值）
   ├─ 确定上下文长度（自适应）
   └─ 归一化处理（可选）

3. 模型推理
   ├─ TimesFMService.predict()
   ├─ TimesFM 2.5 Model
   └─ 返回点预测 + 分位数预测

4. 结果后处理
   ├─ 反归一化
   ├─ 计算统计指标（最小值、最大值、中位数）
   ├─ 判断趋势方向
   └─ 构建 ForecastResult

5. 报告集成
   ├─ 注入到分析结果中
   ├─ 渲染报告模板
   └─ 生成通知消息
```

---

## 4. 实现细节

### 4.1 依赖管理

**requirements.txt 新增**:
```
timesfm>=2.5.0
torch>=2.0.0  # 或 jax>=0.4.0
```

**可选依赖**（图表生成）:
```
matplotlib>=3.7.0
plotly>=5.14.0
```

### 4.2 模型下载策略

1. **首次运行**: 从 Hugging Face 自动下载
2. **缓存位置**: `~/.cache/huggingface/hub/`
3. **自定义缓存**: 支持 `HF_HOME` 环境变量
4. **离线支持**: 可预先下载模型文件

### 4.3 内存管理

**懒加载模式**:
```python
class TimesFMService:
    _model: Optional[TimesFM_2p5_200M_torch] = None
    _lock = threading.Lock()

    def _ensure_model_loaded(self):
        """线程安全的懒加载"""
        if self._model is None:
            with self._lock:
                if self._model is None:  # 双检锁
                    self._model = self._load_model()
```

**内存占用**:
- 模型权重: ~800MB
- 运行时开销: ~500MB
- 总计: ~1.5GB

### 4.4 错误处理

**异常处理策略**:
```python
try:
    forecast = timesfm_service.predict(prices, horizon=60)
except ModelNotLoadedError:
    # 记录警告，继续主流程
    logger.warning("TimesFM model not loaded, skipping prediction")
except InsufficientDataError:
    # 数据不足，跳过预测
    logger.warning(f"Insufficient data for {stock_code}")
except Exception as e:
    # 其他错误，不影响主流程
    logger.error(f"TimesFM prediction failed: {e}")
```

### 4.5 性能优化

**批处理支持**:
```python
def predict_batch(
    self,
    price_series_list: List[np.ndarray],
    horizon: int = 60
) -> List[ForecastResult]:
    """批量预测多只股票"""
    # 利用 TimesFM 的批处理能力
```

**缓存策略**:
- 模型缓存: 进程内单例
- 预测结果缓存: 可选（Redis / 文件）
- 缓存失效: 每日收盘后

---

## 5. 报告集成

### 5.1 报告结构

在现有分析报告中增加章节：

```markdown
## AI 预测参考

> ⚠️ **免责声明**: 以下预测由 AI 模型生成，仅供参考，不构成投资建议。

### 预测概要

- **预测周期**: 未来 60 个交易日
- **当前价格**: ¥150.00
- **预测中位数**: ¥165.00 (+10.0%)
- **预测区间**: ¥140.00 - ¥185.00 (80% 置信区间)
- **趋势判断**: ↗️ 上涨

### 详细预测

| 日期 | 中位数预测 | 10% 分位数 | 90% 分位数 |
|------|-----------|-----------|-----------|
| T+1  | ¥151.20   | ¥148.50   | ¥154.00   |
| T+2  | ¥152.10   | ¥149.00   | ¥155.50   |
| ...  | ...       | ...       | ...       |

[查看预测图表]
```

### 5.2 模板文件

**新增模板** (`templates/forecast_section.zh.jinja2`):
```jinja2
{% if forecast_result %}
## AI 预测参考

> ⚠️ **免责声明**: 以下预测由 AI 模型生成，仅供参考，不构成投资建议。

### 预测概要

- **预测周期**: 未来 {{ forecast_result.horizon }} 个交易日
- **当前价格**: {{ format_price(forecast_result.current_price) }}
- **预测中位数**: {{ format_price(forecast_result.median_predicted) }}
  ({{ format_change(forecast_result.median_predicted, forecast_result.current_price) }})
- **预测区间**: {{ format_price(forecast_result.min_predicted) }} -
  {{ format_price(forecast_result.max_predicted) }} (80% 置信区间)
- **趋势判断**: {{ trend_emoji(forecast_result.trend_direction) }}
  {{ trend_label(forecast_result.trend_direction) }}

{% if show_detail %}
### 详细预测

{% include 'forecast_table.zh.jinja2' %}
{% endif %}

{% if show_chart %}
![预测曲线]({{ forecast_chart_url }})
{% endif %}

{% endif %}
```

### 5.3 多语言支持

- 中文模板: `templates/forecast_section.zh.jinja2`
- 英文模板: `templates/forecast_section.en.jinja2`
- 根据 `REPORT_LANGUAGE` 环境变量选择

---

## 6. 配置管理

### 6.1 环境变量

在 `.env.example` 中新增：

```bash
# ===================================
# TimesFM AI 预测配置
# ===================================
# 是否启用 TimesFM 预测（默认 false）
TIMESFM_ENABLED=false
# 模型 ID（Hugging Face 模型标识）
TIMESFM_MODEL_ID=google/timesfm-2.5-200m-pytorch
# 最大上下文长度（0 = 自适应，最大 16384）
TIMESFM_MAX_CONTEXT=0
# 最大预测天数（默认 60）
TIMESFM_MAX_HORIZON=60
# 模型缓存目录（留空使用默认）
TIMESFM_CACHE_DIR=
# 推理设备（auto/cpu/cuda）
TIMESFM_DEVICE=auto
# 是否使用连续分位数头（推荐开启）
TIMESFM_USE_QUANTILE_HEAD=true
```

### 6.2 Web 设置集成

在系统设置页新增"AI 预测"分组：

```python
# src/core/config_registry.py

ConfigRegistry.register_group("ai_forecast", {
    "title": "AI 预测",
    "description": "TimesFM 股价预测配置",
    "fields": [
        {
            "key": "TIMESFM_ENABLED",
            "type": "boolean",
            "label": "启用 AI 预测",
            "description": "在分析报告中包含 TimesFM 模型预测"
        },
        {
            "key": "TIMESFM_MAX_HORIZON",
            "type": "integer",
            "label": "预测天数",
            "min": 1,
            "max": 120,
            "default": 60
        },
        # ... 其他字段
    ]
})
```

---

## 7. 测试策略

### 7.1 单元测试

**测试文件** (`tests/test_timesfm_service.py`):
```python
def test_model_loading():
    """测试模型加载"""
    service = TimesFMService(config)
    service.load_model()
    assert service.is_available()

def test_prediction_shape():
    """测试预测输出形状"""
    result = service.predict(prices, horizon=60)
    assert result.point_forecast.shape == (60,)
    assert result.quantile_forecast.shape == (60, 10)

def test_insufficient_data():
    """测试数据不足场景"""
    with pytest.raises(InsufficientDataError):
        service.predict(prices=np.array([1, 2, 3]), horizon=60)

def test_adaptive_context():
    """测试自适应上下文"""
    short_prices = np.random.rand(100)
    long_prices = np.random.rand(2000)
    # 验证上下文长度自适应
```

### 7.2 集成测试

**测试场景**:
1. 完整分析流程集成
2. 报告生成验证
3. 错误降级处理
4. 多语言报告输出

### 7.3 性能测试

**测试指标**:
- 模型加载时间
- 单次预测延迟
- 批量预测吞吐量
- 内存占用峰值

---

## 8. 部署考虑

### 8.1 Docker 环境

**Dockerfile 更新**:
```dockerfile
# 安装 PyTorch（CPU 版本）
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

# 安装 TimesFM
RUN pip install timesfm[torch]

# 预加载模型（可选）
RUN python -c "import timesfm; timesfm.TimesFM_2p5_200M_torch.from_pretrained('google/timesfm-2.5-200m-pytorch')"

# 持久化缓存
VOLUME ["/root/.cache/huggingface"]
```

### 8.2 GitHub Actions

**CI 配置** (`.github/workflows/ci.yml`):
```yaml
  # TimesFM 依赖安装测试
  - name: Install TimesFM
    run: pip install timesfm[torch]

  # 单元测试
  - name: Test TimesFM Service
    run: pytest tests/test_timesfm_service.py -v
```

### 8.3 资源限制

**建议配置**:
- **最小**: 2 CPU + 4GB RAM（仅 CPU 推理）
- **推荐**: 4 CPU + 8GB RAM（CPU 推理 + 缓存）
- **GPU**: 支持 CUDA 11.x + 4GB VRAM

---

## 9. 风险与限制

### 9.1 技术风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 模型下载失败 | 功能不可用 | 提供离线安装指南 |
| 内存不足 | 崩溃 | 懒加载 + 可配置禁用 |
| 推理超时 | 性能下降 | 超时控制 + 降级处理 |
| 数据质量差 | 预测不准确 | 数据验证 + 异常检测 |

### 9.2 业务风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 用户过度依赖 | 投资损失 | 明确免责声明 |
| 预测不准确 | 信任下降 | 标注参考性质 |
| 合规问题 | 法律风险 | 强调"不构成投资建议" |

### 9.3 已知限制

1. **单变量预测**: TimesFM 主要针对单变量时间序列，不考虑外部因素
2. **历史依赖**: 预测质量高度依赖历史数据质量
3. **不确定性**: 股票市场受多种因素影响，AI 预测仅供参考
4. **黑盒模型**: 无法解释预测依据

---

## 10. 未来增强

### Phase 2 功能（可选）

1. **预测图表生成**:
   - 使用 matplotlib/plotly 生成交互式图表
   - 支持历史数据 + 预测 + 置信区间

2. **历史准确率追踪**:
   - 记录历史预测与实际对比
   - 计算预测准确率指标
   - 自动调整预测置信度

3. **协变量支持** (XReg):
   - 结合成交量、技术指标等外部变量
   - 提高预测准确性

4. **多模型集成**:
   - 集成多个时间序列模型
   - 模型融合提高鲁棒性

5. **实时预测更新**:
   - 盘中实时更新预测
   - 动态调整预测参数

---

## 11. 实施计划

### 11.1 开发阶段

**阶段 1: 核心功能** (预计 3-5 天)
- [ ] 实现 TimesFMService
- [ ] 添加 ForecastResult schema
- [ ] 集成到分析流程
- [ ] 更新报告模板

**阶段 2: 配置与测试** (预计 2-3 天)
- [ ] 添加配置管理
- [ ] 编写单元测试
- [ ] 集成测试
- [ ] 文档更新

**阶段 3: 部署与优化** (预计 2-3 天)
- [ ] Docker 镜像更新
- [ ] 性能优化
- [ ] 错误处理完善
- [ ] 用户文档

### 11.2 验收标准

- [x] TimesFM 模型成功加载
- [x] 能够生成 60 天股价预测
- [x] 预测结果正确集成到报告中
- [x] 支持 `TIMESFM_ENABLED=false` 禁用功能
- [x] 预测失败不影响主分析流程
- [x] 中英文报告正确渲染
- [x] 单元测试覆盖率 > 80%

---

## 12. 参考资料

- [TimesFM GitHub](https://github.com/google-research/timesfm)
- [TimesFM 论文](https://arxiv.org/abs/2310.10688)
- [TimesFM Hugging Face](https://huggingface.co/google/timesfm-2.5-200m-pytorch)
- [A_STOCK_GUIDE.md](https://github.com/google-research/timesfm/blob/master/A_STOCK_GUIDE.md)

---

**文档版本**: 1.0
**最后更新**: 2026-04-15
