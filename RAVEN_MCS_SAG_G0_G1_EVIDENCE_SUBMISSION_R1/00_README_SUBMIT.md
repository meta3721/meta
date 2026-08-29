# RAVEN-MCS SAG G0/G1 Evidence Submission R1

Date: 2026-08-29  
Branch: `raven_sag_g0_g1`  
Commit: `bf04ff4` (pushed to `origin/raven_sag_g0_g1`)  
Authority: `_handoff_sag_v1.1/` (copied under `authority/`)

## 本轮是否完成

**已完成指令授权的补充实验（G0 + G1 5-seed），并已按模板出报告。**  
**尚未得到可进入论文全量实验的 GO。本轮科学结论是 REPAIR。**

按 `RAVEN_MCS_Cursor_SAG_G0_G1_Experiment_Instruction_v1.0.txt` 第 25 节：

| 步骤 | 状态 |
|---|---|
| 单元测试 `tests/unit/test_sag_timing.py` | 完成，PASS |
| G0 smoke（SensorScope, seed 30001, 6 windows） | 完成，PASS |
| G0 full（SensorScope + U-Air, seeds 30001–30003） | 完成，**PASS**（1620 window rows） |
| G1 5-seed（seeds 30001–30005） | 完成 |
| G1 报告 + 五项 Gate 判定 | 完成，**REPAIR** |
| G1 同配置重跑 | 完成，数字与首轮一致（确定性） |
| 10-seed / E1–E5 / T-Drive / 见结果后改 τ | **按指令未做** |

不要把本包解读成“SAG 已经可以写进论文主实验”。Gate 从未打开，SAG 与 No-Design 逐点相同。

## 执行结论

Executive verdict: **REPAIR**

| Gate | 结果 | 含义 |
|---|---|---|
| Gate-1 Predictability | PASS | 实现顺序、冻结、EventTrace、禁止特征均通过 |
| Gate-2 Certificate | FAIL | 联合覆盖低于 0.90 开发地板；`C_cov` 定义不可用 |
| Gate-3 Safety | PASS | SAG false-enable = 0（因为它从未 ON） |
| Gate-4 Prediction | PASS | 相对 No-Design 的 RMSE / WorstGroup 伤害 = 0 |
| Gate-5 Utility | FAIL | ON rate = 0；退化为 Always-No-Design |

关键数字：

- SAG ON rate = **0 / 900** windows（冷启动 80 + `OFF_LOW_COVERAGE` 820）
- 预测伤害 = **0**（SAG ≡ No-Design）
- 结构增益 `gain_group` / `gain_cs` = **0**
- Always-Design 的 U-Air active-set mismatch ≈ **46–59%**；SensorScope Always-D mismatch = 0
- 联合证书覆盖：SensorScope 0.89–0.94；U-Air 0.76–0.97（seed 30003 = 0.76）

主导 OFF 原因：实现里的 `C_cov` 是“本窗 R 覆盖了多少 π^tar>0 的 (k,s)”，远低于冻结阈值 `tau_cov=0.05`。  
**未在看见 G1 后下调 τ。** 下一步只有在确认后才做：把 `C_cov` 改成 `F_{r-}`-可测的 opportunity-probability LCB（作用在 `S_tar` 上），然后重跑 G0 smoke/full + G1 5-seed。

## 包内目录

```
00_README_SUBMIT.md
MANIFEST.json
report/
  SAG_G0_G1_REPORT.md
  G1_VERDICT.json
g0/                 # G0 规定产物 + 冻结配置 + smoke 归档
g1/                 # G1 规定五表 + 5-seed 配置
configs/
  thresholds.json   # G0/G1 冻结阈值
plan/
  SAG_IMPLEMENTATION_PLAN.md
authority/          # 本轮理论/实验口令原文
```

未纳入本包（避免膨胀或重复）：

- `outputs/sag_g1/archive_rerun_20260829-122556/`（首轮 G1 的逐文件备份，数字与现行 `g1/` 相同）
- `outputs/sag_g0/logs/*.json`（运行日志；审计结论已在 `g0/`）
- 论文 Overleaf、`paper_ready_r2/`、密封 E1–E4、`post_review/`、T-Drive seal

## 如何核验

1. 读 `report/SAG_G0_G1_REPORT.md` 与 `report/G1_VERDICT.json`。
2. 对照 `g0/G0_IMPLEMENTATION_AUDIT.md`：必须为 PASS。
3. 对照 `g1/G1_METHOD_SUMMARY.csv`：每个 seed 上 `raven_sag` 与 `raven_wo_design` 的 RMSE / WorstGroup / Δ 相同，且 `Gate_ON_rate=0`。
4. 对照 `g1/G1_PREDICTION_SAFETY.csv`：相对伤害全 0。
5. 阈值哈希应与配置一致：`threshold_hash = 526343535887e2f1094916be22d0403032fab0b905e74ac588f2b1bc6613510e`。
