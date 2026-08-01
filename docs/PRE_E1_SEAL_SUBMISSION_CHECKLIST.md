# RAVEN-MCS Pre-E1 Seal 提交资料清单

## 1. 提交目标

本轮应提交一套能够由教师在独立环境中复核的 Pre-E1 Seal 证据，而不是只
提交实验结果摘要。

只有以下条件全部满足后，才可将状态写为：

```text
P10-R1 = PASS
PRE-E1-SEAL = PASS
E1 = READY_FOR_TEACHER_AUTHORIZATION
E2-E9 = NOT STARTED
```

学生不得自行写 `E1 AUTHORIZED`。

---

## 2. 最终对外提交的三个文件

### 2.1 完整证据包

```text
RAVEN_MCS_PRE_E1_SEAL_EVIDENCE.zip
```

必须包含代码、冻结配置、两次 Smoke、审计结果、测试日志、Git 证明和状态
文件。详细目录见第 3 节。

### 2.2 正式审核报告

优先提交：

```text
PRE_E1_SEAL_REPORT.docx
```

同时保留可审计的 Markdown 源文件：

```text
PRE_E1_SEAL_REPORT.md
```

### 2.3 简短提交说明

```text
SUBMISSION_README.txt
```

必须写明：

1. 最终 Git commit；
2. 证据包 SHA256；
3. 正式报告文件名；
4. 两个 Pre-E1 Smoke run ID；
5. 全量 pytest 结果；
6. solver fallback 结果；
7. S_max 审计结果；
8. q 特征审计结果；
9. 当前 E1 状态；
10. 已知剩余问题。

---

## 3. 证据包内部标准目录

建议按下列结构组织：

```text
RAVEN_MCS_PRE_E1_SEAL_EVIDENCE/
├── 00_submission/
│   ├── SUBMISSION_README.txt
│   ├── PRE_E1_SEAL_REPORT.md
│   └── PRE_E1_SEAL_REPORT.docx
├── 01_git/
│   ├── GIT_STATUS.txt
│   ├── GIT_LOG.txt
│   └── GIT_DIFF_SUMMARY.txt
├── 02_code/
│   └── RAVEN_MCS_PRE_E1_SEAL_CODE.zip
├── 03_frozen_identity/
│   ├── FROZEN_CONFIG_MANIFEST.json
│   ├── DATA_MANIFEST.json
│   ├── EVENT_TRACE_MANIFEST.json
│   ├── TARGET_GROUP_MANIFEST.json
│   └── configs/
├── 04_event_trace/
│   ├── event_trace_ref.json
│   └── events.parquet
├── 05_audits/
│   ├── PRE_E1_SOLVER_AUDIT.json
│   ├── PRE_E1_TIME_STALENESS_AUDIT.json
│   ├── PRE_E1_METRIC_AUDIT.json
│   ├── Q_FEATURE_AUDIT.csv
│   ├── Q_FEATURE_WHITELIST.yaml
│   └── FEDAVG_TWOSTAGE_DIAGNOSTIC.parquet
├── 06_tests/
│   ├── PYTEST_FULL.log
│   ├── PYTEST_PRE_E1.log
│   └── PIP_CHECK.log
├── 07_runs/
│   ├── PRE_E1_SMOKE_RUN1/
│   └── PRE_E1_SMOKE_RUN2/
├── 08_project_status/
│   ├── STATUS.md
│   ├── ISSUES.md
│   ├── CHANGELOG.md
│   ├── FORMULA_TO_CODE_MAP.md
│   └── DATA_DICTIONARY.md
└── 09_hashes/
    ├── EVIDENCE_SHA256.txt
    └── FILE_HASHES.json
```

---

## 4. 完整代码包

文件名：

```text
RAVEN_MCS_PRE_E1_SEAL_CODE.zip
```

必须包含：

```text
src/
scripts/
tests/
configs/
docs/
pyproject.toml
requirements.txt
requirements-lock.txt
environment.yml
README.md
STATUS.md
ISSUES.md
CHANGELOG.md
Makefile
```

必须排除：

```text
.git/
.venv/
__pycache__/
.pytest_cache/
*.pyc
data/raw/
旧 outputs/
临时文件
编辑器缓存
API key
账号凭据
私人绝对路径
```

代码包必须从最终 clean commit 导出，不能直接压缩 dirty worktree。

---

## 5. Git 正式证明

### 5.1 GIT_STATUS.txt

包含：

```bash
git rev-parse HEAD
git status --porcelain
```

验收标准：

```text
git status --porcelain
```

输出为空。

### 5.2 GIT_LOG.txt

包含：

```bash
git log -5 --oneline
```

### 5.3 GIT_DIFF_SUMMARY.txt

包含：

```bash
git diff --stat <P10基线提交>..HEAD
```

当前 P10 基线提交为：

```text
b4f1661944e100b86295da6583d6449106e7c8af
```

---

## 6. 冻结配置与身份

必须提交：

```text
configs/frozen/e1_sensorscope_balanced.yaml
configs/frozen/e1_sensorscope_groups.yaml
configs/frozen/pre_e1_smoke.yaml
FROZEN_CONFIG_MANIFEST.json
```

`FROZEN_CONFIG_MANIFEST.json` 至少包含：

```text
config_sha256
data_sha256
event_trace_sha256
target_group_sha256
git_commit
freeze_timestamp
validation_summary
solver_configuration
s_max
no_harm_threshold
e1_methods
e1_seeds
```

E1 方法必须明确列出五个正式方法；随机种子必须明确列出五个固定 seed。

`e1_sensorscope_groups.yaml` 必须说明：

```text
G=4 仅用于 SensorScope E1 门控；
不自动作为 E2-E9 或其他数据集的唯一分组方案。
```

所有冻结文件必须绑定最终 Git commit，而不是当前基线 commit。

---

## 7. 数据与 EventTrace 清单

必须提交：

```text
DATA_MANIFEST.json
EVENT_TRACE_MANIFEST.json
TARGET_GROUP_MANIFEST.json
event_trace_ref.json
events.parquet
```

清单至少记录：

- 数据来源和许可证；
- 原始文件名、大小和 SHA256；
- 处理文件名、大小和 SHA256；
- 数据维度；
- train/validation/test 划分；
- 客户端划分规则；
- 窗口数及时间范围；
- EventTrace 生成参数；
- S_max；
- target group 映射；
- 各组支持数；
- unsupported group 数；
- 生成代码版本和最终 Git commit。

不要求上传 1 GB 以上的原始数据，但必须确保教师能够根据清单重新下载并
验证。

---

## 8. P2 求解器封口

必须提交：

```text
solver_diagnostics.parquet
PRE_E1_SOLVER_AUDIT.json
```

每个 RAVEN 窗口至少记录：

```text
window_id
primary_solver
primary_status
objective_value
simplex_residual
nonnegative_violation
upper_bound_violation
ess_l2_violation
solve_time_seconds
fallback_triggered
fallback_solver
fallback_status
accepted_solver
accepted_status
```

硬门：

```text
abs(sum(alpha) - 1) <= 1e-7
min(alpha) >= -1e-8
max(alpha - alpha_bar) <= 1e-7
sum(alpha**2) - 1/E_bar <= 1e-7
```

`optimal_inaccurate` 必须触发重新求解或 fallback。fallback 仍失败时：

```text
run = FAIL
```

不得静默替换为均匀权重。

---

## 9. S_max 与时序封口

必须提交：

```text
PRE_E1_TIME_STALENESS_AUDIT.json
```

至少包含：

```text
s_max
chronological_windows
window_overlap_count
future_leakage_count
tau_consistency_violations
usable_over_smax_count
expired_but_usable_count
missing_checkpoint_count
```

必须验证：

```text
U == 1  =>  0 <= tau <= S_max
tau > S_max  =>  U == 0
```

`tau <= num_windows` 不能替代 S_max 门。

建议将 S_max 同时写入：

- EventTrace metadata；
- frozen config；
- run manifest；
- time/staleness audit；
- unit tests。

---

## 10. q 特征与 deadline_slack_pre

必须提交：

```text
Q_FEATURE_AUDIT.csv
Q_FEATURE_WHITELIST.yaml
DATA_DICTIONARY.md
```

数据字典必须明确：

```text
deadline_slack_pre =
window_close_time - registration_time
```

并证明该特征在注册时即可确定，不读取：

- 实际完成时间；
- 实际网络时延；
- 实际到达时间；
- 当前更新或更新范数；
- 当前损失改善；
- 窗口关闭后的任何信息。

q 审计最终状态只能是：

```text
NO_FORBIDDEN_FEATURES
```

或：

```text
REVIEWED_WHITELIST_ONLY
```

---

## 11. 测试证据

必须保存完整终端输出：

```text
PYTEST_FULL.log
PYTEST_PRE_E1.log
PIP_CHECK.log
```

执行：

```bash
pytest -q
pytest -q tests/unit/test_pre_e1_*.py
pytest -q tests/integration/test_pre_e1_smoke.py
pip check
```

至少新增并通过：

```text
test_solver_fallback_on_inaccurate_status
test_solver_residual_hard_gate
test_usable_implies_tau_within_smax
test_stale_expired_update_is_unusable
test_deadline_slack_is_pre_outcome
test_git_worktree_clean_for_e1
test_frozen_config_matches_commit
test_pre_e1_smoke_reproducible
```

日志不能只写人工摘要，必须保留真实命令、stdout、stderr、返回码、Python
版本和执行时间。

---

## 12. 两次独立 Pre-E1 Smoke

必须提交：

```text
outputs/runs/PRE_E1_SMOKE_RUN1/
outputs/runs/PRE_E1_SMOKE_RUN2/
```

每个目录包含：

```text
manifest.json
resolved_config.yaml
event_trace_ref.json
metrics_window.parquet
metrics_run.json
predictions_test.parquet
arrival_weights_test.parquet
propensity_diagnostics.parquet
solver_diagnostics.parquet
system_metrics.json
smoke_checks.json
checkpoints/
stdout.log
stderr.log
```

双跑复现门：

```text
git_commit 相同
config_hash 相同
data_hash 相同
event_trace_hash 相同
target_group_hash 相同
predictions 在冻结容差内一致
核心 metrics 在冻结容差内一致
```

两个 run 都必须基于最终 clean commit。现有 P10-R1 run 可用作实现参考，
但不能直接替代 clean-commit Pre-E1 run。

---

## 13. 指标与方法诊断

### 13.1 PRE_E1_METRIC_AUDIT.json

必须从 `predictions_test.parquet` 独立重算：

```text
RMSE_mu
RMSE_rho
Gap_mis
```

逐方法验证：

```text
abs(Gap_mis - (RMSE_mu - RMSE_rho)) <= 1e-12
```

同时报告：

```text
sum_target_weights
sum_arrival_weights
target_arrival_l1_gap
zero_arrival_weight_units
support_violations
```

### 13.2 FEDAVG_TWOSTAGE_DIAGNOSTIC.parquet

至少包含：

```text
window_id
client_id
local_weight_diff
beta_vs_fedavg_diff
local_loss_diff
update_hash_equal
model_hash_equal
prediction_max_abs_diff
zeta_summary
p_summary
q_summary
```

---

## 14. 正式报告内容

`PRE_E1_SEAL_REPORT.md/.docx` 必须包含：

1. 修改摘要；
2. 最终 Git commit；
3. Git clean 证明；
4. frozen config 和全部身份哈希；
5. solver 残差门与 fallback 结果；
6. S_max 和 staleness 审计；
7. `deadline_slack_pre` 定义与信息边界；
8. 两次 Smoke 配置和结果；
9. 全量测试结果及日志路径；
10. Pre-E1 门禁逐项结果；
11. 剩余风险；
12. E1 是否可提交教师授权的结论。

不能只写 PASS，必须给出实际数值、容差、run ID 和证据路径。

---

## 15. 当前资料盘点

### 15.1 已有、可复用

- P10-R1 端到端训练实现；
- G=4 SensorScope 时间组配置；
- 原子 arrival weight 和 Gap 指标实现；
- q 白名单与审计基础；
- FedAvg/TwoStage 路径诊断；
- 两次 P10-R1 Smoke；
- R1-G1 至 R1-G8 checker；
- 教师审阅报告和 P10-R1 技术报告；
- 当前全量 pytest 通过记录。

### 15.2 尚不能视为 Pre-E1 Seal 完成

- worktree 仍为 dirty，尚无正式 clean commit；
- frozen config 仍绑定旧基线 commit；
- 缺少 E1 Balanced 和 Pre-E1 专用冻结配置；
- 缺少 S_max 业务上限及过期更新审计；
- 缺少 solver residual 硬门与 `optimal_inaccurate` fallback 证据；
- 缺少 `deadline_slack_pre` 的正式定义、实现证明和测试；
- 缺少 `test_pre_e1_*` 单元/集成测试；
- 缺少真实完整测试日志；
- 缺少 clean-commit 下重新执行的两次 Pre-E1 Smoke；
- 缺少正式 Git 状态证明；
- 缺少最终 Pre-E1 代码包、证据包和 DOCX 报告；
- 当前证据包尚未证明已上传并可由教师下载。

因此，当前状态仍应保持：

```text
P10-R1 = PASS
PRE-E1-SEAL = NOT COMPLETED
E1 = BLOCKED_PENDING_PRE_E1_SEAL_AND_TEACHER_REVIEW
```

---

## 16. 推荐执行顺序

1. 明确并冻结 S_max、五个 E1 方法、五个 seed 和 no-harm 阈值；
2. 实现 solver residual 门与 fallback；
3. 实现 S_max/过期更新门；
4. 明确并测试 `deadline_slack_pre`；
5. 新增 Pre-E1 单元和集成测试；
6. 运行全量测试并保存真实日志；
7. 更新 STATUS、ISSUES、CHANGELOG、公式映射和数据字典；
8. 审阅所有变更并创建正式 Git commit；
9. 确认 `git status --porcelain` 为空；
10. 使用最终 commit 重新冻结所有配置和 manifest；
11. 在最终 commit 上独立运行两次 Pre-E1 Smoke；
12. 执行 solver、S_max、q、metric、reproducibility 全部门禁；
13. 生成 Git 证明和文件哈希；
14. 导出 clean-commit 代码包；
15. 生成 Markdown 和 DOCX 正式报告；
16. 打包证据包并计算 SHA256；
17. 上传三个最终文件并验证教师可下载。

---

## 17. 最终最低验收清单

- [ ] 正式 clean Git commit；
- [ ] `git status --porcelain` 为空；
- [ ] 完整代码包；
- [ ] frozen config 与最终 commit 一致；
- [ ] 数据、EventTrace、target-group manifests；
- [ ] solver residual/fallback PASS；
- [ ] S_max/staleness PASS；
- [ ] q/deadline_slack_pre PASS；
- [ ] 全量 pytest 日志；
- [ ] Pre-E1 专项测试日志；
- [ ] pip check 日志；
- [ ] 两次 clean-commit Pre-E1 Smoke；
- [ ] metric 独立重算 PASS；
- [ ] FedAvg/TwoStage 路径诊断；
- [ ] STATUS/ISSUES/CHANGELOG/公式映射更新；
- [ ] 正式 Markdown/Word 报告；
- [ ] 证据包 SHA256；
- [ ] 三个最终文件已上传且可下载；
- [ ] E1 状态仅写 `READY_FOR_TEACHER_AUTHORIZATION`。

