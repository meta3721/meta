# RAVEN-MCS V2.3 阶段实验报告

**报告范围：** Phase 2（含 2A/2B）→ Phase 9；含 E0 与硬门 G0–G5  
**日期：** 2026-07-31  
**工作区：** `D:\Cursor\raven.mcs`  
**宪法 / 指令：** V2.3（`参考文件/RAVEN-MCS_V2.3_Cursor_实验执行指令.txt`）  
**版本标签（CHANGELOG）：** 0.3.0 → 0.4.0  
**主实验状态：** **未启动**（E1/G6–G7 未授权）

---

## 0. 执行摘要

本阶段完成了论文实验所需的**数据冻结（G0）**、**公式单元验收（E0）**，以及 **Target / EventTrace / Common-NDMF / WindowRunner / propensity / 聚合器 / P2·debt** 核心骨架，并取得可执行硬门 **G0–G5 全部 PASS**。

全量单元测试约 **89 passed**。  
**不得**据此启动 Balanced E1 或 20-seed 主实验：ISSUE-012（方法集/阈值冲突）仍待教师确认；完整方法名册与实验入口（`run_experiment.py`）尚未齐备。

| 里程碑 | 状态 |
|--------|------|
| Phase 2A 数据框架 | DONE |
| Phase 2B 四真实适配器 + G0 | DONE / PASS |
| E0.1–E0.6 | DONE / PASS |
| Phase 3–9 核心 | DONE（Phase 8 方法名册 PARTIAL） |
| G1–G5 | PASS |
| E1 / G6–G7 / 主实验 | BLOCKED |

---

## 1. 本阶段完成内容

### 1.1 Phase 2A — 数据框架

- 规范 `atomic_units.parquet` / `client_measurements.parquet` schema 与校验
- 时间槽 60/20/20 划分 + train 前 20% warm-up；禁止 split 重叠
- 仅用 train 估计标准化统计；源值哈希
- T-Drive 身份级 30/70 fleet 分离契约
- 适配器契约、synthetic fixture、审计与 raw/interim/processed SHA-256 manifest
- CLI：`scripts/prepare_data.py`、`scripts/audit_data.py`

### 1.2 Phase 2B — 官方数据与 G0

- 可审计下载：`scripts/download_data.py` + provenance / checksum
- 真实适配器冻结：`sensorscope` / `uair` / `traffic` / `tdrive_speed`
- Traffic 连续窗口硬底线通过（**43×720**；优选 ≥60 站未达 → ISSUE-013）
- G0 检查器：`scripts/check_g0_data.py` → `docs/audits/g0_data_check.json`
- 字典：`docs/DATA_DICTIONARY.md`

### 1.3 E0 — 公式单元套件

| 子项 | 内容 | 模块 |
|------|------|------|
| E0.1 | 手算权重 ζ̂ / a / m / ā / c / ESS / d / b / β | `correction/*` |
| E0.2 | IPW Monte Carlo | `correction/ipw.py` |
| E0.3 | P2 唯一性（CLARABEL） | `aggregation/p2_cvxpy.py` |
| E0.4 | debt 前缀界 | `aggregation/debt.py`, `metrics/debt.py` |
| E0.5 | 窗口时序（θ 冻结 / 一更 / 空窗） | `training/window_timing.py` |
| E0.6 | q 特征泄漏静态扫描 | `propensity/leakage.py` |

入口：`scripts/check_e0.py` → `docs/audits/e0_unit_check.json`

### 1.4 Phase 3–9 — 算法核心与 G1–G5

| Phase | 完成项 |
|-------|--------|
| 3 | `TargetBuilder` / `GroupMapper` / `StrataMapper`；support/mass 审计 |
| 4 | 不可变 EventTrace（Parquet + metadata + trace hash）；篡改可检出 |
| 5 | `CommonNDMF` 共享骨干；禁止 client embedding |
| 6 | `WindowRunner` + WindowClock 不变量 |
| 7 | 滞后 Observation / Usable propensity + opportunity EMA |
| 8 | Aggregator 接口；**FedAvg / FedAsync / TwoStage-Hajek / RAVEN** |
| 9 | P2（CVXPY+CLARABEL）与 debt 接入 runner；G3–G5 可执行检查 |

硬门入口：`scripts/check_hard_gates.py` → `docs/audits/hard_gates_g1_g5.json`

---

## 2. 新增 / 修改文件（要点）

### 数据与配置

- `configs/dataset/{sensorscope,uair,traffic,tdrive_speed}.yaml`
- `configs/experiment/{E0_unit,E1_balanced}.yaml`（E1 仅为声明，未授权运行）
- `data/processed/{四数据集}/`、`data/manifests/`、`docs/DATA_DICTIONARY.md`

### 核心源码（`src/raven_mcs/`）

- `data/`：schema、split、scaling、fleet、pipeline、四适配器、`target.py`
- `correction/`：design_ratio、hajek、ESS、second_stage、ipw
- `aggregation/`：feasibility、debt、p2_cvxpy、base、methods
- `simulation/event_trace.py`
- `models/common_ndmf.py`
- `training/window_timing.py`、`window_runner.py`
- `propensity/`：observation、usable、leakage
- `opportunities/`：strata、estimator
- `metrics/debt.py`

### 脚本与测试

- `scripts/{download_data,prepare_data,audit_data,check_g0_data,check_e0,check_hard_gates}.py`
- `tests/unit/test_data_*.py`、`test_e0_*.py`、`test_phase3_target_strata.py`、`test_phase4_to_9_gates.py`
- 审计 JSON：`docs/audits/{g0_data_check,e0_unit_check,hard_gates_g1_g5,*_audit}.json`

### 文档

- `STATUS.md`、`CHANGELOG.md`、`ISSUES.md`、`docs/FORMULA_TO_CODE_MAP.md`（同步）

**明确不存在（外部方案曾误引）：**  
`scripts/run_experiment.py`、`aggregation/p2_solver.py`、`tests/unit/test_hajek.py`

---

## 3. 关键设计决策

1. **数据先冻结再算法：** Phase 2B 官方下载 + SHA-256；synthetic 不得静默替代真实数据。  
2. **Traffic 不停换数据集：** 硬底线 ≥30×336 满足（取 43×720）；优选 60 站记入 ISSUE-013，禁止 PEMS 替换。  
3. **E0 与流水线解耦：** 公式在合成/手算夹具上验收；不依赖主实验 run。  
4. **EventTrace 不可变：** freeze + hash；方法间必须共享同一 trace_hash（G1）。  
5. **时间语义严格：** 窗内 θ 冻结；active 仅一次全局更新；空窗不更新（G2）。  
6. **P2 不读当前 update：** `solve_p2` 无 `u` 参数；α 与更新坐标解耦（G4）。  
7. **Phase 8 先交付核心四方法：** FedAvg / FedAsync / TwoStage / RAVEN；完整 12 方法 + 消融列为后续（PARTIAL）。  
8. **E1 YAML 只声明不执行：** 待 ISSUE-012 与实验入口齐备后再开。

---

## 4. 对应论文公式

（详见 `docs/FORMULA_TO_CODE_MAP.md`；本阶段已落地的主要条目）

| 公式簇 | 代表符号 | 代码落点 | 验收 |
|--------|----------|----------|------|
| F1 | 原子单元 / 组 / 层 / μ·ν | `data/schema.py`, `data/target.py`, `opportunities/strata.py` | Phase3 + G0 schema |
| F1.4 | Common-NDMF `f_θ` | `models/common_ndmf.py` | Phase5；禁 client embed |
| F2 | 窗口 / R / O / E / U / A | `event_trace.py`, `window_runner.py`, propensity | G1–G2；E0.5–E0.6 |
| F3 | ζ̂ / a / m / ā / c / n_eff | `correction/*`, `opportunities/estimator.py` | E0.1–E0.2；G3 |
| F5 | d / b / β̂ | `correction/second_stage.py` | E0.1；G3 |
| F6 | ω / Q / P2 / 约束 | `aggregation/debt.py`, `p2_cvxpy.py`, `feasibility.py` | E0.3–E0.4；G4–G5 |

尚未作为本阶段数值结论的部分：完整本地目标 F4、主指标 RMSE 流水线 F7+、SimOracle（G7）、E1 no-harm（G6）。

---

## 5. 运行的命令

验收复跑（2026-07-31，项目 `.venv` Python 3.11.8）：

```powershell
cd D:\Cursor\raven.mcs
.\.venv\Scripts\Activate.ps1

python scripts/verify_run.py --check-environment
python scripts/verify_run.py --check-repository --require-git
python scripts/check_g0_data.py --data-root data
python scripts/check_e0.py
python scripts/check_hard_gates.py
python -m pytest tests/unit/test_phase3_target_strata.py -q
python -m pytest tests/unit/test_phase4_to_9_gates.py -q
python -m pytest -q
```

人工抽查示例：

```powershell
python -c "import pandas as pd; a=pd.read_parquet('data/processed/sensorscope/atomic_units.parquet'); print(sorted(a.columns)); print(a['split'].value_counts())"
python -c "from raven_mcs.aggregation.methods import get_aggregator; print([get_aggregator(m) for m in ['fedavg','fedasync','twostage_hajek','raven']])"
```

---

## 6. 测试结果

| 套件 | 结果 |
|------|------|
| ENVIRONMENT CHECK | PASSED（Python 3.11.8） |
| REPOSITORY CHECK | PASSED |
| G0 | **PASS**（sensorscope / uair / traffic / tdrive_speed） |
| E0 | **PASS**（9 tests；六组件均为 true） |
| G1–G5 | **PASS**（见下节数值摘要） |
| Phase3 单测 | 4 passed |
| Phase4–9 单测 | 5 passed |
| 全量 pytest | **约 89 passed**，exit code 0 |

**说明：** G4/P2 求解过程中 CLARABEL 可能打印 `Solution may be inaccurate` UserWarning；硬门仍报 `status_solver: optimal` 且 `G4: PASS`。属求解器告警，不单独记为硬门失败，但应在后续规模实验中监控。

### 人工抽查摘要（2026-07-31）

- SensorScope `atomic_units` 列齐全；split 计数约 train 10285 / val 3465 / test 3410；时间单调  
- Traffic：`43` stations × `720` hours  
- 四聚合器可实例化；Common-NDMF 文档与 API 明确禁止 client embedding  

---

## 7. 硬门状态

| Gate | 状态 | 证据要点 |
|------|------|----------|
| **G0** | **PASS** | `docs/audits/g0_data_check.json`；四分集 manifest/split/scaling/disjoint |
| **G1** | **PASS** | `tamper_detected=true`；`trace_hash=7acf1fabb6bc36c0660841840d92821e20a31b99753e55b38dd3a49a70b83e88` |
| **G2** | **PASS** | 4 windows / 4 active；θ 一更与空窗语义 |
| **G3** | **PASS** | `m=42`；`n_eff≈4.642105`；β≈`[0.189, 0.270, 0.541]` |
| **G4** | **PASS** | CLARABEL `optimal`；α 和≈1 |
| **G5** | **PASS** | `debt_l1≈0.003086`（前缀界成立） |
| **G6** | Pending | E1 Balanced no-harm；**未跑** |
| **G7** | Pending | SimOracle 排序；**未跑** |

机器可读：`docs/audits/hard_gates_g1_g5.json`（`"passed": true`）

---

## 8. 发现的问题

| ID | 摘要 | 对主实验影响 |
|----|------|----------------|
| **ISSUE-012** | 绑定指令 vs DOCX：E1 方法集与阈值冲突（3% vs 2% 等） | **阻塞 E1** |
| **ISSUE-011** | `E1_balanced.yaml` 含 TimeAlign 等；完整 runner/实验入口未齐；YAML 仅声明 | 阻塞 E1 执行 |
| **ISSUE-010** | `configs/frozen/` 与完整 test-entry 拒绝门未完 | 任意 test 评估前阻塞 |
| **ISSUE-013** | Traffic 优选 ≥60 站未达（43×720） | 不挡 G0 硬底线；需知情 |
| ISSUE-003/004/009 | 遗留空文件 / 文档对齐 / 工作区杂质 | 低；不挡本阶段 |

外部（DeepSeek）验证路径 `p2_solver.py` / `run_experiment.py` / `test_hajek.py` **与仓库不符**，不得作为失败依据。

---

## 9. 尚未完成事项

1. 完整 Phase 8 方法名册（Central-*、TimeAlign、FLAMF、Local-Hajek、Inst-Cal、Debt-Cal、SimOracle、消融等）  
2. `p2_projected.py` 规模求解器（小规模可继续用 CVXPY）  
3. Phase 10：完整 RMSE / 伪指标 / 伪分布产物流水线  
4. 实验入口：`scripts/run_experiment.py`（或等价 Hydra 入口）与 dry-run  
5. ISSUE-010 测试集入口冻结门  
6. E1 / G6、G7，以及 E2–E9 / 20-seed 主实验  
7. 论文图表与最终复现包  

---

## 10. 下一步动作

1. **教师确认 ISSUE-012**：最终 E1 方法集与 no-harm 阈值（建议书面冻结）。  
2. 实现缺失 E1 方法（至少 TimeAlign，若指令锁定该方法集）并补齐实验入口。  
3. 完成 ISSUE-010 test-entry 拒绝与 frozen config hash。  
4. 仅在 E0 + G0–G5 已通过（本报告已满足）且上述 1–3 就绪后，启动 **E1 Balanced / G6**。  
5. G6–G7 通过后，再冻结 20-seed 主实验。

**本阶段正式结论：**  
Phase 2–9 核心与硬门 G0–G5 **验收通过，可归档保留**；**禁止**进入主实验与 E1，直至 ISSUE-012 及实验入口就绪。

---

## 附录 A — 四数据集 G0 快照

| Dataset | G0 | 形状 / 备注 |
|---------|----|-------------|
| sensorscope | PASS | 55×312，coverage 1.0 |
| uair | PASS | 36×264，coverage 1.0 |
| traffic | PASS | **43×720**；优选 60 站未达（ISSUE-013） |
| tdrive_speed | PASS | 500 m / 30 min；fleet 30/70 |

## 附录 B — 证据文件索引

| 文件 | 用途 |
|------|------|
| `docs/audits/g0_data_check.json` | G0 |
| `docs/audits/e0_unit_check.json` | E0 |
| `docs/audits/hard_gates_g1_g5.json` | G1–G5 |
| `docs/audits/{dataset}_audit.json` | 各数据集审计 |
| `STATUS.md` | 工程状态总表 |
| `ISSUES.md` | 开放问题 |
| `docs/FORMULA_TO_CODE_MAP.md` | 公式→代码映射 |
| `CHANGELOG.md` | 0.3.0–0.4.0 变更 |

## 附录 C — 授权边界说明

用户明确授权并验收至 **E0**；随后「请完成后续步骤」被实现为 Phase 3–9 / G1–G5。本报告按用户决定 **保留该验收**，并将 Phase 3–9 结果一并归档。E1 及主实验仍不在授权范围内。
