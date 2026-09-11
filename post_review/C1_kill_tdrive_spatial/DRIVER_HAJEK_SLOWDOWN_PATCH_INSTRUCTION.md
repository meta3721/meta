# 指令：修 C1 T-Drive 驱动的 Hájek 内存泄漏式变慢（可停当前格）

人已授权：**可以停掉正在跑的 TwoStage-Hájek 种子 31001**。不要改科学合同，不要改 φ / EventTrace / processed 哈希 / Table II。不要开 CUDA（`extract_features` 的 index 仍在 CPU）。不要 commit，除非人再要求。

把这份文件交给执行 AI。只改 `scripts/run_c1_tdrive_spatial.py` 里 `train_one` 的猴子补丁。不要改 `src/raven_mcs/opportunities/estimator.py`、`src/raven_mcs/training/window_runner.py`、`src/raven_mcs/aggregation/methods.py`。

```text
You are the C1-KILL driver patcher for repo C:\Cursor\raven.mcs.
Python: C:\Cursor\raven.mcs\.venv_new\Scripts\python.exe
Driver: scripts/run_c1_tdrive_spatial.py
Spec: post_review/C1_kill_tdrive_spatial/TARGET_SPEC.json (LOCKED, do not edit)
Traces: artifacts/e3_c1_tdrive_spatial_eventtraces_v1/ (do not regenerate)
Keep: results_c1_kill/round_v1/runs/tdrive_spatial_h/fedavg_window/seed31001/C1_ACCEPTED.json
Discard: incomplete twostage_hajek seed31001 (no C1_ACCEPTED exists; stop the process)
Device stays cpu. Do not retune phi, p_obs, s_max, lambdas, grid, or windows after RMSE.
Do not edit the manuscript. Do not start City Scanner ingest/train.
```

## 0. 为什么要改（不要再诊断一遍）

Hájek 比上次 UTC 矩阵慢约 40 倍，**不是**占用变多：C1 迹与 UTC 迹都是 441898 行、高峰 4071 client。FedAvg 两次都是 CPU、约 37 分钟。

根因在 `train_one` 的 `_lagged_light`：

```python
if runner.policy.uses_observation_ipw or runner.policy.uses_usable_ipw:
    return orig_lagged(window_slice, client_data)
```

Hájek / ObsUse / FedAU / raven 都会走完整 `_update_lagged_estimators`。其中 `OpportunityEstimator.update_window` 对冻结 support 里 **每一对** `(client, stratum)`（本块约 24926 对）每窗 `diagnostics.append` 一次，且 **不清空**。第 48 窗约 120 万条 dict。随后 `_pw` 里 **每窗 `gc.collect()`**，堆越大 GC 越慢。日志已从 6 秒/窗涨到约 15 分钟/窗。

FedAvg 不带 IPW，走 light 路径（`est.diagnostics = []`），所以正常。

Zeta 本块用冻结 `pi_opp_joint`，不读 `opportunity_estimator.pi_hat()`。诊断列表对训练权重不是必要的。

## 1. 先停进程

当前 `--stage train` 是进程树，不要只杀外壳：

- 外壳 PID 曾为 6376（`python scripts/run_c1_tdrive_spatial.py --stage train`）
- 子进程才是真正训练（曾见 PID 16984，`Python311\python.exe` 同一命令行）

用命令行确认后再杀：

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -match 'run_c1_tdrive_spatial.py --stage train' } |
  Select-Object ProcessId, ParentProcessId, CommandLine
```

对匹配到的 **全部** PID 执行 `Stop-Process -Id <pid> -Force`。确认没有残留后再改代码。

不要删：

- `results_c1_kill/round_v1/runs/tdrive_spatial_h/fedavg_window/seed31001/C1_ACCEPTED.json`
- `C1_SCD_FREEZE.json` / `GO.json` / 十条 EventTrace

可以删（若出现）：`results_c1_kill/round_v1/runs/tdrive_spatial_h/twostage_hajek/seed31001/`（不应有 `C1_ACCEPTED.json`）。Ledger 里若有未完成的 Hájek 31001 行，删掉该行，避免误当完成。

## 2. 只改 `train_one` 里两处补丁

文件：`scripts/run_c1_tdrive_spatial.py`。科学数字、种子、方法列表、`_device()` 仍返回 `"cpu"`。

### 2.1 `_lagged_light`：IPW 方法也不得堆积诊断

**禁止** 再 `if uses_observation_ipw or uses_usable_ipw: return orig_lagged(...)`。

改为固定两段，对所有方法执行：

**A. Opportunity EMA，无诊断（已有 light 循环，保留）**

- 统计本窗 `(client, stratum)` 计数
- 更新 FedAU 的 attempt/usable 计数（FedAU 需要）
- 若 `opportunity_estimator` 存在且方法需要 opp/IPW/design：只更新 `est.counts` 的 EMA
- **每窗** `est.diagnostics = []`
- **不要**调用 `est.update_window`（那会 `sorted` 全 support、append 诊断、再 `pi_hat()`）
- **不要** `for key in sorted(est.counts)` 扫 2.5 万冻结钥匙；只扫 `set(est.counts) | set(本窗计数)` 也可以，但必须清空 diagnostics。更省：只对「本窗出现的 key ∪ 已有 counts」做 EMA，与现有 light 循环相同。

**B. 若 `uses_observation_ipw` 或 `uses_usable_ipw`：更新 p/q 模型，但不写历史**

从 `orig_lagged` / `window_runner._update_lagged_estimators` 抄 **更新** 调用：

- `obs_propensity.update_records_after_completion(...)`
- `usable_propensity.update_lagged(...)`（仅 `attempted==1`）
- `p_model_version` / `q_model_version` 仍递增

**不要** `p_propensity_history.append`、`q_propensity_history.append`、`q_attempt_diagnostics.append`。若必须调用 `orig_lagged`，事后立刻：

```python
runner.p_propensity_history.clear()
runner.q_propensity_history.clear()
runner.q_attempt_diagnostics.clear()
if runner.opportunity_estimator is not None:
    runner.opportunity_estimator.diagnostics = []
```

优先不要调用 `orig_lagged`（避免每窗建造 2.5 万条诊断再扔掉）。p/q 的 `update_*` 必须保留，否则 IPW 权重会变。

### 2.2 `_pw`：不要每窗 `gc.collect()`

现码在删完无用 checkpoint 之后无条件 `gc.collect()`。改为：

- **删掉每窗 `gc.collect()`**，或每 20 窗最多一次
- 继续按 `future_versions` 删 `model_versions`（低内存仍需要）
- 心跳日志保留

## 3. 验收（改完立刻做，先于全矩阵）

1. `python scripts/run_c1_tdrive_spatial.py --stage train`  
   - `[1/50] fedavg_window seed31001` 必须 `status=REUSED`  
   - `[2/50] twostage_hajek seed31001` 重新开跑（CPU）
2. 看前 10 窗墙钟：应与 FedAvg 同量级（大约数秒到几十秒），**禁止**再出现 6s→900s 的单调爆炸。若第 8–10 窗已超过 120 秒且仍在涨，停下来，说明 diagnostics/gc 没切干净。
3. 任务管理器：Hájek 工作集应稳定在约 2 GB 量级，不应每窗涨几百 MB。
4. 科学不变：仍 178 窗、`REAL_PATH_EXECUTED`、φ 不重算、不改 EventTrace 哈希。
5. 全 50 格跑完后再 `--stage tables`（`--stage train` 结束会自己 `stage_tables`）。`c1_kill` 门槛未变。

## 4. 明确不要做

- 不要改 `TARGET_SPEC.json`、φ、`p_obs`、`s_max`、λ、网格、窗口数
- 不要重生成 31001–31010 EventTrace
- 不要改 `data/processed/tdrive_speed/`
- 不要把 `_device()` 改回 cuda
- 不要改全局 `estimator.py` / `window_runner.py`（P2 那次是实验内 clip，这次同样只动本驱动）
- 不要动 Table II / hybrid 表 / 手稿
- 不要开 City Scanner ingest
- 不要把未完成的 Hájek 半格写成 `C1_ACCEPTED`

## 5. 完成后写三行日志

在 `results_c1_kill/round_v1/EXECUTION_LOG.md` 记：停了哪个 PID、驱动改了 `_lagged_light`/`_pw`、FedAvg 31001 REUSED、Hájek 31001 从窗 1 重开。不要写 RMSE 对比来回滚补丁。
