# 指令：用 City Scanner 纽约 PM2.5 关掉 C1

本文件是实验授权。作者占位符不改。参考文献本轮不核。
**本轮不训练**，直到 T-Drive spatial C1 矩阵不再占用本机，且 `LICENSE.json` 已从 Zenodo 记录页抄下许可证。

```text
You are the C1-KILL planner/executor for repo C:\Cursor\raven.mcs.
Canonical manuscript: TO_OVERLEAF_paper_tmc_r1_clean/main.tex
Python: C:\Cursor\raven.mcs\.venv_new\Scripts\python.exe
Paper method: SCD via phi=0, NOT coverage Gate.
Do not overwrite tdrive_protocol_seal_r1/.
Do not mix into tab:main_effectiveness or change Table II / tab:tdrive_hybrid / tab:traffic_four_region.
Do not overlay GPS on SensorScope/U-Air.
Do not use T-Drive/Porto/TLC speed as Y.
Do not treat City Scanner vehicles as FL clients.
Do not use build_pi_target_support_compatible.
Do not retune phi, p_obs, s_max, grid, slot, windows, or lambdas after RMSE.
Do not restore formal non-inferior on Table II.
Do not commit unless asked.
Do not start --stage train on this host while results_c1_kill/ is still training.
Kill bar is frozen below BEFORE RMSE. Missing the bar is a legal negative, not a retune trigger.
```

## 0. 为什么是这一块，怎样才算杀掉

审稿 C1：现实移动场上 SCD 不赢 FedAU/ObsUse。T-Drive 速度场即使用四象限目标，仍可能失败（Y 从同一条 GPS 来）。NSW-Traffic 四区域是协议 \(R\)，不能关 C1。

City Scanner 纽约：市政车机会采样，校准后的 **PM2.5 是独立场 Y**，GPS 只决定格子占用。这不是 T-Drive 克隆，也不是把出租轨迹叠到站点气温上。

**C1_KILL=true** 当且仅当：本块 10 种子配对上，SCD 相对 **FedAU 和 ObsUse** 的均值相对差，在 **WorstGroupRMSE 或 RMSE_μ** 上 **同时** \(\le -0.5\%\)。矩阵完整但未过门槛：`AUDIT.status=PASS` 且 `c1_kill=false`。禁止把未过门槛写成赢。

\(O/U\) 仍是 \(p_{\mathrm{obs}}=0.35\), \(s_{\max}=5\)。标签必须写 hybrid。不是端到端 MCS。

## 1. 冻结科学合同

| 层 | 本轮 | 禁止写成 |
|---|---|---|
| 数据 | Zenodo `10.5281/zenodo.7961851` 的纽约 PM CSV（Pilot1 + Pilot2 PM 三片） | 波士顿 1 辆实验车；贝鲁特（需另锁）；NO2 文件；自己爬 Senseable 地图 |
| \(Y\) | 格子×30 min 内有限 `pm25` 的均值，单位 μg/m³ | 速度、行程量、NO2（本锁）、用 RMSE 换 \(Y\) |
| 原子单元 | 500 m 等距网格 × 30 min，至少一条有效 PM2.5 | 为 RMSE 改 200 m/1 h；填补从未被访问的格子 |
| Client | **`spatial_id`（格子）** | 把 5 辆车当 FL client |
| \(h(i)\) | 全部格子中位数 \(g_x,g_y\) 四象限，无 \(Y\) | UTC H1–H4；按 RMSE 调边界 |
| \(\boldsymbol\mu\) | test-split 区域份额，无 \(Y\) | 用 PM 标签 |
| \(\phi\) | 训练 unique `unit_id` 上 \(\pi_i^{\mathrm{tar}}=\mu_{h(i)}\)；\(\mathrm{Design}=\mathrm{ON}\iff\phi=0\) | 看完 RMSE 再决定开不开 Design |
| \(s(i)\) | `region::block::weekday`（最多 32） | 继续用 cell 级 stratum 却宣称 \(\phi=0\) |
| \(R\) | 该格子在该 30 min 是否有 City Scanner 样本 | 协议 always-on；T-Drive 占用 |
| \(O/U\) | Complete-aligned \(p_{\mathrm{obs}}=0.35\), \(s_{\max}=5\) | 声称联合实测网络日志 |
| 种子 | `32001–32010` | 复用 30001 / 31001 任何旧 EventTrace |
| 窗口 | **100**（预注册，与 P2 相同量级） | 为 RMSE 改 50/178 |

先抄许可证，再 ingest，再算 \(\phi\)，写入 `GO.json`，再生成 EventTrace，再训练。

物理过滤（冻结）：丢掉非有限 lat/lon/time/`pm25`；丢掉 `pm25 < 0` 或 `> 1000`。禁止用验证 RMSE 收紧阈值。

Ingest 失败则停，**不要**改成贝鲁特或改网格。贝鲁特只有另一次人锁才允许。

## 2. 路径（尚未创建结果；未授权下载前不要占满磁盘）

- 规格：`post_review/C1_kill_cityscanner/TARGET_SPEC.json`
- 原始：`data/raw/cityscanner_nyc_pm25/`（ingest 时写入）
- 许可证：`data/raw/cityscanner_nyc_pm25/LICENSE.json`（必须从 Zenodo 记录页抄，不得编造）
- 处理后：`data/processed/cityscanner_nyc_pm25/`（新目录；禁止改已有 processed 哈希）
- 结果：`results_c1_cityscanner/round_v1/`
- Trace：`artifacts/e3_c1_cityscanner_eventtraces_v1/`
- 驱动：尚未写；ingest 完成且本机 T-Drive C1 结束后再写 `scripts/run_c1_cityscanner.py`

设备：与 P2/C1 相同，feature index 在 CPU 上。驱动里 `_device()` 固定 `"cpu"`。不要改全局 `training/client.py`。

## 3. 写作（仅当 `c1_kill=true` 且矩阵 PASS）

独立附录表，不并入 Table II。可写：City Scanner 纽约机会采样；\(Y=\) 校准 PM2.5；格子为联邦单元；\(R\) 为真实到访；\(O/U\) 受控；\(\phi=0\) 规则在 RMSE 之前冻结；Design 因 \(\phi=0\) 而开；不是端到端 MCS；车队只有数辆，故 client 是格子不是车辆。

若 `c1_kill=false`：**不要**改主文主张。只写 `C1_KILL_REPORT.md`。

## 4. 人已锁定

`TARGET_SPEC.json` `status=LOCKED`，`chosen_option=CS_NYC_PM25_CELL_500M`。
2026-09-10 用户确认选择 City Scanner。本锁是纽约 PM2.5，不是波士顿、不是贝鲁特、不是 Air View。
