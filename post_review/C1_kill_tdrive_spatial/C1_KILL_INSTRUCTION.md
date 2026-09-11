# 指令：用 T-Drive 四象限目标关掉 C1

本文件是实验授权。作者占位符不改。参考文献本轮不核。

```text
You are the C1-KILL executor for repo C:\Cursor\raven.mcs.
Canonical manuscript: TO_OVERLEAF_paper_tmc_r1_clean/main.tex
Python: C:\Cursor\raven.mcs\.venv_new\Scripts\python.exe
Paper method: SCD via phi=0, NOT coverage Gate.
Do not overwrite tdrive_protocol_seal_r1/.
Do not mix into tab:main_effectiveness or change Table II / tab:tdrive_hybrid numbers.
Do not overlay GPS on SensorScope/U-Air.
Do not use build_pi_target_support_compatible.
Do not retune phi, p_obs, s_max, or lambdas after RMSE.
Do not restore formal non-inferior on Table II.
Do not commit unless asked.
Kill bar is frozen below BEFORE RMSE. Missing the bar is a legal negative, not a retune trigger.
```

## 0. C1 是什么、怎样才算杀掉

审稿 C1：最现实场景（T-Drive）SCD 比 FedAU/ObsUse 差 **+2.39%/+2.43%**；站点表只是不差。结构指标不算用户可感知回报。

现有 hybrid 表 **关着 Design**（\(\phi=47.4\%\)）。UTC 目标上的 full-Design 诊断行更差。那张表不能关 C1。

NSW-Traffic 四区域是协议 \(R\)，也不能关 C1。

本轮 **C1_KILL=true** 当且仅当：在本块 10 种子配对上，SCD 相对 **FedAU 和 ObsUse** 的均值相对差，在 **WorstGroupRMSE 或 RMSE_μ** 上 **同时** \(\le -0.5\%\)（论文自己的“赢”门槛，不是 +0.5% 容差）。矩阵完整但未过门槛：`AUDIT.status=PASS` 且 `c1_kill=false`。禁止把未过门槛写成赢。

联合实测网络 \(U\) 本轮不做（T-Drive 没有设备日志）。\(O\) 仍是 \(p_{\mathrm{obs}}=0.35\)。标签必须写 hybrid。

## 1. 冻结科学合同

| 层 | 本轮 | 禁止写成 |
|---|---|---|
| \(h(i)\) | 北京网格四象限，中位数 \(g_x,g_y\) 在全部 cell 上冻结，无 \(Y\) | UTC H1–H4；按 RMSE 调边界 |
| \(\boldsymbol\mu\) | test-split 区域份额，无 \(Y\) | 用速度标签 |
| \(\phi\) | 训练 unique `unit_id` 上 \(\pi_i^{\mathrm{tar}}=\mu_{h(i)}\)；\(\mathrm{Design}=\mathrm{ON}\iff\phi=0\) | 用 stratum-in-test 的 47.4% 当本块开关 |
| \(s(i)\) | `region::block::weekday`（最多 32） | 继续用 cell 级 stratum 却宣称 \(\phi=0\) |
| \(R\) | 轨迹占用，与 TD-R-E3 同源 processed 表 | 改 processed 哈希 |
| \(O/U\) | 仍 Complete-aligned \(p_{\mathrm{obs}}=0.35\), \(s_{\max}=5\) | 真实传感器/网络日志 |
| 种子 | `31001–31010` | 复用 30001 UTC EventTrace |
| 窗口 | 178，与 seal 一致 | 为 RMSE 改窗口数 |

先算 \(\phi\)，写入 `GO.json`，再生成 EventTrace，再训练。

## 2. 路径

- 结果：`results_c1_kill/round_v1/`
- Trace：`artifacts/e3_c1_tdrive_spatial_eventtraces_v1/`
- 驱动：`scripts/run_c1_tdrive_spatial.py`
- 规格：`post_review/C1_kill_tdrive_spatial/TARGET_SPEC.json`

不要改 `data/processed/tdrive_speed/`。staging 另写。

## 3. 写作（仅当 `c1_kill=true` 且矩阵 PASS）

独立表，不并入 Table II。可写：same \(\phi=0\) rule frozen before RMSE; Design on because \(\phi=0\); real taxi \(R\); \(O/U\) controlled; not end-to-end MCS。

若 `c1_kill=false`：**不要**改主文主张。只写 `C1_KILL_REPORT.md`。

## 4. 人已锁定

`TARGET_SPEC.json` `status=LOCKED`，`human_signoff` 非空。本轮选 T-Drive 四象限，不选新城市。
