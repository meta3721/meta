# RAVEN-MCS V2.3：P10 端到端训练集成与 P10-R1 审计封口报告

**提交用途：** 教师审阅  
**报告日期：** 2026-08-01  
**代码分支：** `p10-r1-time-metrics-audit`  
**基线提交：** `b4f1661944e100b86295da6583d6449106e7c8af`  
**当前结论：** `P10-R1 = PASS`；`E1 = BLOCKED_PENDING_TEACHER_REVIEW`

---

## 一、执行摘要

P10 的目标是把真实 SensorScope 数据、Common-NDMF 本地训练、两阶段校正、
多方法对照、论文指标和可复现审计接入同一条端到端流水线。

第一次 P10 Smoke 虽然能够运行，但后续审计发现其不能作为 E1 的可靠入口：

1. `RMSE_rho` 实际使用了均匀权重；
2. `Gap_mis` 被错误实现为组间 RMSE 范围；
3. 测试预测一度未加载最终服务器参数；
4. FedAvg 与 TwoStage 的局部/服务器策略没有完全分离；
5. 事件分配使用 Python 随机化 `hash()`，跨进程不可复现；
6. 配置冻结没有在测试预测入口强制执行；
7. 原门禁只检查部分 R1 gates，且存在硬编码 PASS；
8. 空窗口版本、观测顺序与 Hájek 权重存在潜在错位风险。

上述问题已在 P10-R1 中逐项修复。最终使用同一 seed 独立执行两次
SensorScope Smoke，R1-G1 至 R1-G8 全部通过，预测与指标满足规定的复现
容差。本轮没有运行 E1。

---

## 二、实验范围与配置

| 项目 | 最终配置 |
|---|---|
| 数据集 | SensorScope 真实处理后数据 |
| 原子单元数 | 17,160 |
| 测试原子单元数 | 3,410 |
| 模拟客户端数 | 10 |
| 连续时间窗口数 | 20 |
| 随机种子 | 26001 |
| 本地训练步数 | 2 |
| 模型 | Common-NDMF |
| 场景 | `complete_aligned` |
| 方法 | FedAvg-Window、TwoStage-Hajek、RAVEN-MCS |
| E1 主目标组 | G=4，仅使用冻结时间块 |
| 设备 | CPU |
| RAVEN 求解器 | CLARABEL |

冻结身份如下：

- Config SHA256：`fe041ef149c2a4cdea5813aaf797cd0fdae0d1c1caad06fb9f9eb42f23a9c69a`
- Data SHA256：`44081beb40e019ad999dc997162e7c7be9c0eb4cf562cddfb4f570ec1f7cca03`
- EventTrace SHA256：`cf222dd992429c268b7f3baab03f1634b7ef4217f2b961166c87a88fd7a2a215`
- Target-group SHA256：`21682c7adef8e7e8661a1fa6251d49fc13dcef8715f101f3cea14a1380afce65`

---

## 三、端到端流水线

每个窗口按以下顺序执行：

1. 读取当前服务器参数与版本；
2. 从冻结 EventTrace 读取风险集；
3. 仅使用历史窗口状态计算 opportunity、p、q 与 variance；
4. 形成客户端局部训练集合；
5. 在读取本窗口 `U` 前冻结尝试集合；
6. 从客户端实际下载的历史 checkpoint 执行 Common-NDMF 本地 SGD；
7. 根据 EventTrace 的 `U` 形成可聚合集合；
8. 按 MethodPolicy 选择局部权重与服务器权重；
9. 每窗口至多执行一次全局更新；
10. 仅 RAVEN 更新 debt；
11. 保存窗口指标、参数哈希与诊断；
12. 窗口关闭后才更新 opportunity、p、q 和 variance，供后续窗口使用。

测试预测入口会重新加载最终服务器 `theta`，并在预测前验证冻结配置、
数据、EventTrace 和目标组哈希。

---

## 四、时间因果与版本审计

窗口由排序后的唯一 `time_index` 切分为连续块，不使用 modulo。审计结果：

| 检查项 | 结果 |
|---|---:|
| 窗口数 | 20 |
| 使用 modulo | 否 |
| 窗口重叠数 | 0 |
| 时间逆序数 | 0 |
| 未来记录泄漏数 | 0 |
| 重复原子分配数 | 0 |
| 未分配原子数 | 0 |
| tau 一致性违规数 | 0 |

EventTrace 强制：

`0 <= tau = window_id - downloaded_version <= num_windows`

空窗口会发布“参数不变但版本递增”的 checkpoint，因此后续客户端不会因
窗口号与模型版本脱节而加载不存在的版本。

---

## 五、目标风险与到达风险

目标权重由冻结测试支持构造。到达强度按原子单元计算：

`r_hat_i = sum_k(pi_hat_opp[k,s(i)] * nu_hat_k[i|s(i)] * p_hat_obs[k,i] * q_hat_use[k,s(i)])`

随后在测试支持上归一化得到 `arrival_weight`。该过程只读取训练/预热阶段
冻结估计器，不读取测试预测误差或残差。

审计结果：

| 检查项 | 结果 |
|---|---:|
| target weight 总和 | 1.0 |
| arrival weight 总和 | 1.0 |
| 最小 arrival weight | 0.0001810062 |
| 最大 arrival weight | 0.0003628993 |
| target-arrival L1 距离 | 0.13949978 |
| 零权重原子数 | 0 |
| 支持违规数 | 0 |

因此，`complete_aligned` 场景下目标风险与到达风险确实分离，并未退化为
均匀权重。

---

## 六、指标定义与最终结果

严格使用：

- `RMSE_mu = sqrt(sum_i target_weight_i * error_i^2)`
- `RMSE_rho = sqrt(sum_i arrival_weight_i * error_i^2)`
- `Gap_mis = RMSE_mu - RMSE_rho`

门禁会从 `predictions_test.parquet` 独立重算两个 RMSE，并要求每个方法满足：

`abs(Gap_mis - (RMSE_mu - RMSE_rho)) <= 1e-12`

最终 run `P10_SMOKE_20260801_102515`：

| 方法 | RMSE_mu | RMSE_rho | Gap_mis | 平均训练损失 | 中位 n_eff |
|---|---:|---:|---:|---:|---:|
| FedAvg-Window | 7.181765 | 7.064596 | 0.117169 | 7.837601 | 16.2546 |
| TwoStage-Hajek | 7.157197 | 7.039968 | 0.117229 | 7.910788 | 16.2546 |
| RAVEN-MCS | 7.111120 | 6.993705 | 0.117415 | 7.907508 | 16.2546 |

这些数值仅用于验证流水线和指标正确性，不用于宣称 RAVEN 已在正式 E1
实验中优于基线。本轮没有做面向 RMSE 的参数调优。

---

## 七、FedAvg 与 TwoStage-Hajek 差异诊断

诊断覆盖 200 个窗口—客户端记录，比较局部权重、alpha/beta、局部损失、
更新向量哈希、全局模型哈希及最终预测。

| 诊断量 | 结果 |
|---|---:|
| 最大局部权重绝对差 | 0.0615661 |
| 最大 alpha 差 | 0.0815881 |
| 最大 beta 与 FedAvg 权重差 | 0.0815881 |
| 最大局部损失差 | 2.2788601 |
| 所有更新哈希是否相同 | 否 |
| 所有模型哈希是否相同 | 否 |
| 最终预测最大绝对差 | 0.0313680 |

结论：FedAvg 使用原始观测样本数和均匀局部损失；TwoStage 使用 Hájek
局部损失与 beta 服务器权重。两条计算路径已实际分离，不是数值退化。

---

## 八、q 特征泄漏审计

q 模型运行时输入仅包含：

- `bias`
- `model_age`
- `device_class`
- `network_budget`
- `deadline_slack`

源代码扫描中出现的 `arrival` 仅位于 simulator truth，用于构造 `U` 标签，
已通过显式白名单记录文件、符号、原因和允许角色。

最终状态：`REVIEWED_WHITELIST_ONLY`，无未审阅的禁用特征。

---

## 九、冻结目标组与可达性

SensorScope E1 主目标组冻结为 G=4 时间块，不引入缺乏坐标依据的空间划分。
原 220 个 station×time 组仅用于附录诊断，不进入主 debt 约束。

| 组 | 支持原子数 | 有效客户端累计数 | 每窗口平均 usable mass |
|---:|---:|---:|---:|
| 0 | 4,290 | 50 | 23.90 |
| 1 | 4,290 | 58 | 25.25 |
| 2 | 4,290 | 60 | 20.30 |
| 3 | 4,290 | 60 | 20.45 |

`solve_epsilon_reach` 结果：

- `epsilon_reach = 0.00895722`
- solver status：`optimal`
- feasible：`true`
- unsupported positive-target groups：0

---

## 十、R1 硬门结果

| Gate | 内容 | 状态 |
|---|---|---|
| R1-G1 | 连续窗口、无未来泄漏、tau 一致 | PASS |
| R1-G2 | 原子 arrival weights、归一化、非均匀 | PASS |
| R1-G3 | RMSE 与 Gap 数学一致性 | PASS |
| R1-G4 | q 特征泄漏审计 | PASS |
| R1-G5 | FedAvg/TwoStage 路径差异 | PASS |
| R1-G6 | G=4 支持与可达性 | PASS |
| R1-G7 | artifacts 与哈希一致性 | PASS |
| R1-G8 | 同 seed 双跑复现 | PASS |

---

## 十一、复现与测试

最终双跑：

- `outputs/runs/P10_SMOKE_20260801_102055`
- `outputs/runs/P10_SMOKE_20260801_102515`

两次运行满足：

- EventTrace hash 完全相同；
- frozen config hash 完全相同；
- 预测在绝对容差 `1e-10` 内一致；
- 核心指标在绝对容差 `1e-12` 内一致。

测试结果：

| 检查 | 结果 |
|---|---|
| 全量 pytest | 146 passed |
| E0 executable gates | 9 passed |
| G0 数据门 | SensorScope、U-Air、Traffic、T-Drive 全部 PASS |
| 依赖一致性 | `pip check` 无损坏依赖 |
| IDE lints | 无新增错误 |

---

## 十二、Artifacts 与证据

最终 run 包含：

- manifest、resolved config、EventTrace reference；
- window/run metrics；
- test predictions 与 atomic arrival weights；
- propensity、solver、system diagnostics；
- 三个方法的真实模型 checkpoints；
- smoke checks、stdout、stderr。

主要证据：

- 技术审计报告：`docs/reports/P10_R1_TIME_METRICS_AUDIT_REPORT.md`
- 时间审计：`outputs/audits/p10_r1_window_audit.json`
- arrival 审计：`outputs/audits/p10_r1_arrival_weight_audit.json`
- q 审计：`outputs/audits/p10_r1_q_feature_scan.csv`
- 方法差异诊断：`outputs/audits/p10_r1_fedavg_twostage_diagnostic.parquet`
- 目标组可达性：`outputs/audits/p10_r1_group_reachability.json`
- 证据包：`RAVEN_MCS_P10_R1_EVIDENCE.zip`

---

## 十三、已知限制与风险

1. RAVEN 的部分窗口中 CLARABEL 发出 `Solution may be inaccurate` 警告。
   当前结果有限、无 NaN/Inf，R1 gates 均通过，但建议教师决定 E1 前是否
   要求增加求解器 fallback 或更严格的残差阈值。
2. 当前 Git worktree 为 dirty，P10-R1 修改尚未提交。正式归档前应由项目
   负责人审阅变更并创建明确提交。
3. Traffic 数据达到硬下限，但未达到偏好的 60 个站点覆盖；该问题与本次
   SensorScope P10 Smoke 不直接相关。
4. 本轮仅为单 seed 小规模 Smoke，不能替代 E1 的 5-seed Balanced
   no-harm 主实验。

---

## 十四、请教师审阅的决策项

请教师重点确认：

1. 是否认可 SensorScope 主目标组采用 G=4 时间块；
2. 是否认可当前原子 arrival-risk 定义及冻结边界；
3. 是否接受 CLARABEL 警告在 E1 前保留，或要求增加额外求解器门；
4. 是否允许下一轮进入 E1 5-seed Balanced no-harm。

在获得明确批准前，项目状态保持：

`P10-R1 = PASS`  
`E1 = BLOCKED_PENDING_TEACHER_REVIEW`  
`E2-E9 = NOT STARTED`

