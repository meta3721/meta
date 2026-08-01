# E1 人工确认方案

**实验：** E1_balanced — Balanced no-harm gate (5 seeds)  
**数据集：** SensorScope  
**方法：** FedAvg-Window / TimeAlign-Agg / TwoStage-Hajek / RAVEN  
**种子：** 26001, 26002, 26003, 26004, 26005  
**窗口数：** 100  
**创建日期：** 2026-07-31  
**目的：** 在启动 E1 实验前及实验完成后，提供可逐项勾选的人工确认清单

---

## 阶段 A — 前置条件确认（E1 启动前）

> **规则：** 以下项目全部通过后，E1 方可启动。任一未通过则阻塞。

### A.1 硬门 G0–G5 全量通过

| # | 检查项 | 方法 | 预期 | 确认 |
|---|--------|------|------|------|
| A.1.1 | G0 数据检查 | 查看 `docs/audits/g0_data_check.json`，确认 `"passed": true` 且四分集均 PASS | ✅ | ☐ |
| A.1.2 | E0 公式单元 | 查看 `docs/audits/e0_unit_check.json`，确认 `"passed": true` 且六组件均为 `true` | ✅ | ☐ |
| A.1.3 | G1 事件溯源 | 查看 `docs/audits/hard_gates_g1_g5.json`，确认 G1 `"status": "PASS"` 且 `tamper_detected: true` | ✅ | ☐ |
| A.1.4 | G2 窗口时序 | 同上，确认 G2 `"status": "PASS"`，`active_windows == windows` | ✅ | ☐ |
| A.1.5 | G3 权重恒等式 | 同上，确认 G3 `"status": "PASS"`，`m ≈ 42`，`n_eff ≈ 4.64` | ✅ | ☐ |
| A.1.6 | G4 P2 约束 | 同上，确认 G4 `"status": "PASS"`，`status_solver: "optimal"` | ✅ | ☐ |
| A.1.7 | G5 debt 前缀界 | 同上，确认 G5 `"status": "PASS"`，`debt_l1 > 0` | ✅ | ☐ |

**复核命令：**

```powershell
python scripts/check_g0_data.py --data-root data
python scripts/check_e0.py
python scripts/check_hard_gates.py
```

---

### A.2 ISSUE-012 教师确认

> **阻塞级别：HIGH** — 未经确认不得启动 E1。

| # | 检查项 | 详情 | 确认 |
|---|--------|------|------|
| A.2.1 | 方法集确认 | 绑定指令：FedAvg / TimeAlign / TwoStage / RAVEN；设计 DOCX：FedAsync / TwoStage / RAVEN。**请教师书面指定最终方法集。** | ☐ |
| A.2.2 | no-harm 阈值确认 | 绑定指令建议 3% 容忍度；设计 DOCX 指定 2% + CI + clipping <5% + median ESS ≥2。**请教师书面指定最终阈值协议。** | ☐ |
| A.2.3 | 确认记录归档 | 教师书面确认存入 `docs/decisions/ISSUE-012_resolution.md`（或等效位置），并在 ISSUES.md 中标记为 Closed。 | ☐ |

---

### A.3 代码就绪

| # | 检查项 | 方法 | 预期 | 确认 |
|---|--------|------|------|------|
| A.3.1 | E1 方法聚合器 | `python -c "from raven_mcs.aggregation.methods import get_aggregator; [get_aggregator(m) for m in ['fedavg_window','timealign_agg','twostage_hajek','raven']]"` | 四种全部成功，无 KeyError | ☐ |
| A.3.2 | 实验入口 | 确认 `scripts/run_experiment.py` 存在且可执行 `--dry-run` | 文件存在，`--help` 输出正常 | ☐ |
| A.3.3 | E1 自动检查 | `python scripts/check_e1.py` | `config_valid`, `methods`, `runner_exists` 均为 PASS；status 为 READY | ☐ |
| A.3.4 | Common-NDMF 模型 | `python -c "from raven_mcs.models.common_ndmf import CommonNDMF; m=CommonNDMF(n_features=10); print(m)"` | 无报错，输出模型结构 | ☐ |
| A.3.5 | E1 config 冻结 | 确认 `configs/frozen/` 中存在 E1 的 config hash 快照（ISSUE-010 完成后） | hash 文件存在且与当前 YAML 一致 | ☐ |

**自动化复核命令：**

```powershell
python scripts/check_e1.py
python -c "from raven_mcs.aggregation.methods import get_aggregator; [print(get_aggregator(m).name) for m in ['fedavg_window','timealign_agg','twostage_hajek','raven']]"
```

---

## 阶段 B — G6 硬门：Balanced no-harm（实验运行后）

> **G6 定义：** 在 Balanced 场景下，RAVEN-MCS 不得在任一 seed 上显著劣于最强基线（按预注册阈值判定）。
> **通过条件：** 5 个 seed 全部满足 no-harm 约束。

### B.1 运行确认

| # | 检查项 | 方法 | 预期 | 确认 |
|---|--------|------|------|------|
| B.1.1 | 5 seed 全部完成 | 检查 `outputs/runs/E1_balanced/` 下每个 seed 目录存在 `metrics.json` | 5 个 seed 均有输出 | ☐ |
| B.1.2 | 无崩溃/异常退出 | 检查 `outputs/runs/E1_balanced/` 下各 seed 的 `run.log` | 无 `Traceback`、`ERROR`、`exit_code != 0` | ☐ |
| B.1.3 | 窗口数正确 | 每个 seed 的 metrics 中 `num_windows == 100` | 5×100 窗口 | ☐ |
| B.1.4 | 自动 G6 检查 | `python scripts/check_hard_gates.py --gate G6`（待实现） | G6: PASS | ☐ |

---

### B.2 数值审核（人工）

| # | 检查项 | 详情 | 预期 | 确认 |
|---|--------|------|------|------|
| B.2.1 | RAVEN vs 最强基线 | 对于每个 seed，确认 RMSE(RAVEN) ≤ (1 + threshold) × min(RMSE(baselines)) | 5/5 seed 满足 | ☐ |
| B.2.2 | 阈值使用正确 | 确认代码中使用的 no-harm threshold 与 A.2.2 教师确认值一致 | 数值匹配 | ☐ |
| B.2.3 | 基线完整性 | 确认所有声明方法（FedAvg / TimeAlign / TwoStage）均产生有效 RMSE | 无 NaN / Inf | ☐ |
| B.2.4 | ESS 底线 | 若 DOCX 的 median ESS ≥2 被采纳，确认每个 seed 的 median ESS 记录 | ≥2 | ☐ |
| B.2.5 | clipping 检查 | 若 DOCX 的 clipping <5% 被采纳，确认各方法 clipping 比例 | <5% | ☐ |

---

## 阶段 C — G7 硬门：SimOracle 排序（实验运行后）

> **G7 定义：** SimOracle（使用 oracle ζ/p + MC q）应在 RMSE 排序上优于所有实际方法，且与实际 RAVEN 的配对差距（Δ_pair）与跨场景差距（Δ_{c-s}）符合预期方向。

### C.1 运行确认

| # | 检查项 | 方法 | 预期 | 确认 |
|---|--------|------|------|------|
| C.1.1 | SimOracle 方法已实现 | `python -c "from raven_mcs.aggregation.methods import get_aggregator; get_aggregator('simoracle')"` | 无 KeyError | ☐ |
| C.1.2 | Oracle ζ/p 正确注入 | 确认 SimOracle 使用了 frozen oracle 值而非在线估计 | 代码审计确认 | ☐ |
| C.1.3 | MC q 特征使用预生成 | 确认 SimOracle 的 q 特征来自 MC 预生成，不含 post-outcome 信息 | 代码审计确认（E0.6 通过） | ☐ |
| C.1.4 | 自动 G7 检查 | `python scripts/check_hard_gates.py --gate G7`（待实现） | G7: PASS | ☐ |

---

### C.2 数值审核（人工）

| # | 检查项 | 详情 | 预期 | 确认 |
|---|--------|------|------|------|
| C.2.1 | SimOracle RMSE 最优 | 在所有 5 seed 上，确认 SimOracle RMSE < 所有实际方法 RMSE | 5/5 seed | ☐ |
| C.2.2 | Δ_pair 方向 | RAVEN − SimOracle > 0（即 RAVEN 劣于 Oracle） | 5/5 seed 正数 | ☐ |
| C.2.3 | Δ_{c-s} 合理性 | SimOracle 与实际 RAVEN 的差距在不同场景下的一致性（Balanced 场景作为基线） | 无异常反转 | ☐ |
| C.2.4 | 排序一致性 | Kendall τ 或 Spearman ρ：SimOracle 排序与实际方法排序的相关性 | 记录数值，不强制阈值 | ☐ |

---

## 阶段 D — E1 最终验收

> **通过条件：** 阶段 A/B/C 全部勾选完成。

### D.1 可复现性

| # | 检查项 | 方法 | 预期 | 确认 |
|---|--------|------|------|------|
| D.1.1 | 随机种子确定性 | 任选一个 seed（推荐 26001），从 clean 状态重新运行，对比两次 RMSE | 数值一致（浮点误差内） | ☐ |
| D.1.2 | 环境锁定 | `pip freeze` 与 `requirements-lock.txt` 一致 | 无差异 | ☐ |
| D.1.3 | manifest 完整 | `outputs/runs/E1_balanced/` 下存在完整 manifest（config hash + data hash + trace hash） | 文件存在且可解析 | ☐ |

---

### D.2 审计产物

| # | 检查项 | 方法 | 预期 | 确认 |
|---|--------|------|------|------|
| D.2.1 | E1 审计 JSON | 确认 `docs/audits/e1_check.json` 更新为最终状态 | `"status": "READY"`, `"passed": true` | ☐ |
| D.2.2 | G6/G7 审计 JSON | 确认 `docs/audits/hard_gates_g6_g7.json`（或等效）存在且全部 PASS | 文件存在，G6/G7 均为 PASS | ☐ |
| D.2.3 | 证据文件索引 | 更新 `docs/reports/` 下阶段报告，添加 E1 章节 | 报告含 E1 结果摘要 | ☐ |

---

### D.3 最终签字

| # | 角色 | 确认内容 | 签字 / 日期 |
|---|------|----------|-------------|
| D.3.1 | 执行者 | 确认 E1 实验按要求完成，无异常 | ___________ / ______ |
| D.3.2 | 审核者（教师） | 确认方法集、阈值、G6/G7 全部通过 | ___________ / ______ |

---

## 附录 — 命令速查

```powershell
# ---- 前置条件 ----
python scripts/check_g0_data.py --data-root data
python scripts/check_e0.py
python scripts/check_hard_gates.py
python scripts/check_e1.py

# ---- 方法可用性 ----
python -c "from raven_mcs.aggregation.methods import get_aggregator; [print(get_aggregator(m).name) for m in ['fedavg_window','timealign_agg','twostage_hajek','raven']]"

# ---- 模型可用性 ----
python -c "from raven_mcs.models.common_ndmf import CommonNDMF; m=CommonNDMF(n_features=10); print(type(m).__name__)"

# ---- E1 运行（待 run_experiment.py 就绪后） ----
python scripts/run_experiment.py --experiment E1_balanced --dry-run
python scripts/run_experiment.py --experiment E1_balanced --seed 26001
# ... 所有 5 seed ...

# ---- G6/G7 检查（待 check_hard_gates.py 扩展后） ----
python scripts/check_hard_gates.py --gate G6
python scripts/check_hard_gates.py --gate G7
```

---

## 附录 — 参考文件索引

| 文件 | 用途 |
|------|------|
| `configs/experiment/E1_balanced.yaml` | E1 实验配置 |
| `docs/audits/g0_data_check.json` | G0 数据质量证据 |
| `docs/audits/e0_unit_check.json` | E0 公式单元证据 |
| `docs/audits/hard_gates_g1_g5.json` | G1–G5 硬门证据 |
| `docs/audits/e1_check.json` | E1 自动就绪检查输出 |
| `ISSUES.md` | ISSUE-011 / ISSUE-012 详情 |
| `docs/SOURCES.md` | 文档权威链 + E1 冲突说明 |
| `docs/FORMULA_TO_CODE_MAP.md` | G6/G7 定义 |
| `docs/IMPLEMENTATION_PLAN.md` | 整体阶段与门禁 |
