# RAVEN-MCS V2.3 实验报告

**文档版本:** V2.3-REPORT-1.0
**编制日期:** 2026年8月1日

---

## 文档摘要

本报告记录 RAVEN-MCS 项目从 Phase 0 到 Phase 10 的完整实施过程。已通过 G0–G5 全部硬门，完成 E0 公式单元验证（89 tests PASS），实现全部 12 种聚合方法。E1 代码层面已就绪，仅待教师确认 ISSUE-012。

---

## 1. 实验目标与研究问题

| RQ | 问题 | 状态 |
|----|------|------|
| RQ1 | 目标风险错位是否存在 | 指标已实现，待 E2 |
| RQ2 | RAVEN 能否改善目标风险 | 方法已实现，待 E3 |
| RQ3 | 组件是否必要 | 消融框架已实现，待 E4 |
| RQ4 | 估计误差下是否稳健 | 场景已就绪，待 E6-E7 |
| RQ5 | 理论量是否与实测一致 | E0 通过，待 E5 |
| RQ6 | 系统代价是否可接受 | 指标已实现，待 E8 |

---

## 2. 硬门状态

| 硬门 | 描述 | 状态 |
|------|------|------|
| G0 | 数据完整性 | PASS |
| G1 | 事件复现 | PASS |
| G2 | 时间模型(theta frozen) | PASS |
| G3 | 权重正确(m=42, n_eff=4.64) | PASS |
| G4 | P2 正确(CLARABEL optimal) | PASS |
| G5 | 债务恒等式(debt_l1=0.003) | PASS |
| G6 | 平衡场景 no-harm | 待 E1 |
| G7 | Oracle 排序 | 待 E1 |

---

## 3. 数据集审计 (G0)

所有 4 个数据集 G0 检查全部 PASS：sensorscope(55x312), uair(36x264), traffic(43x720), tdrive_speed(500m/30min)。

---

## 4. 方法实现 (12/12)

Central-All, Central-Delivered, FedAvg-Window, FedAsync-Window, TimeAlign-Agg, FLAMF-Original, Local-Hajek, TwoStage-Hajek, Inst-Cal, Debt-Cal, RAVEN-MCS, RAVEN-SimOracle。

---

## 5. E0 公式单元验证

E0.1 Hajek权重, E0.2 IPW收敛, E0.3 P2唯一性, E0.4 债务前缀, E0.5 窗口时序, E0.6 q泄漏——全部 PASS，89 tests。

---

## 6. E1 就绪状态

- 方法可用性: PASS (TimeAlign 已实现)
- run_experiment.py: PASS
- G0/E0/G1-G5: 全部 PASS
- **唯一阻塞: ISSUE-012** (教师确认方法集 FedAvg vs FedAsync + 阈值 2% vs 3%)

---

## 7. 实验矩阵

| 实验 | 状态 |
|------|------|
| E0 | DONE |
| E1 | BLOCKED (ISSUE-012) |
| E2-E9 | 依赖 E1 |
