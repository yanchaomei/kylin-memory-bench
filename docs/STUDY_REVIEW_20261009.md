# Study 限定独立只读审查 · 2026-10-09

## 结论

确认 **2 项 P1**，均通过临时目录、合成数据及内存 mock 离线复现；没有另列未经复现的 P2。现有 `tests/test_study.py` 的 **5 项测试通过，8.677 秒，退出码 0**，但未覆盖这两个路径。仅交付本报告，不改源码、测试、评分语义或 Git。

本报告不能判定正在运行的正式六轮是否受影响：用户说明其使用固定旧调度器快照，本次没有访问该快照、远程机器或正式结果目录。以下行号针对本地 `scripts/run_study.py`。

## P1-1：事件日志跟随符号链接，最终拒绝发生在越界写入之后

- **位置**：`scripts/run_study.py:149-150`；相关路径预检 `124-125`、冻结计划读取 `117-119`、最终清单构建 `179`。核心参照：`evidence.py:27-36`、`131-139`。
- **触发条件**：已有有效冻结计划且仍有待启动 trial，`output/events.jsonl` 被替换或预置为指向输出目录外文件的符号链接。
- **问题**：预检使用 `confined_file` 保护 trial 路径，却没有保护控制器日志。事件处理直接 `open('a')`，会追加到链接目标。`build_manifest` 最终拒绝该链接，但此时目标文件已被修改，不能算 fail-closed。
- **离线复现**：在临时目录中，以 `generate(19, 1)` 的第一个 case 和 fixture 配置创建 study；首次将 `study.run_benchmark` mock 为创建 trial 目录前抛出 `RuntimeError`，获得保留冻结计划的未完成 study。创建目录外 `outside.txt`，写入一行 `sentinel`，再令 `study/events.jsonl` 指向它。恢复时仅 mock `kylin_memory_bench.runner.execute` 返回合法合成 JSON 响应，其余 runner、证据与事件逻辑均真实执行。
- **实测结果**：`outside.txt` 从 **1 行变成 5 行**，新增 4 行真实 trial 进度事件；随后才抛出 `ValueError: symlink evidence is not accepted`。
- **影响**：恢复不可信或被更改的输出目录时，可以在目录外追加写入内容；末尾校验失败无法撤销副作用。该问题不是模型行为，也不依赖真实凭据。
- **修复方向（本轮不实施）**：在启动任何 worker 前检查所有控制文件，并在打开锁、计划、事件日志时采用不跟随链接的文件描述符打开与类型/身份检查；事件文件尤其需要在实际打开时拒绝链接，不能只依赖末尾 manifest。不要通过修改核心评分模块修复控制器文件安全。

## P1-2：启动前失败没有持久化 trial 标记，恢复会选择性重跑并覆盖失败历史

- **位置**：`scripts/run_study.py:130-140`、`155-156`、`168-171`、`178`。
- **触发条件**：worker 在 `run_benchmark` 建立 trial 目录前失败，例如调度时检测到核心源码漂移；随后源码恢复为冻结版本，再对同一目录 resume。
- **问题**：首次失败仅写进 `study-progress.json` / `study.json`，不会创建对应 trial 目录。恢复只检查 trial 路径存在与否，不读取既有失败账本；不存在的路径重新进入 pending。成功后两个汇总文件被替换，原异常不再出现在保留证据中。这与冻结策略 `no phase splicing or selective retry` 不一致。
- **离线复现**：对单 case、单 repeat 的 study，仅将 `source_fingerprint` 三次返回值设为 `[真实核心指纹, 'synthetic-source-drift', 真实核心指纹]`，分别对应冻结定义、worker 启动前检查、最终检查。首次确实走入源码漂移拒绝分支，没有 mock 异常处理逻辑。随后移除该 mock，保持同一数据、配置、输出目录，恢复；仅 mock runner 的执行边界为合成响应，不调用模型。
- **实测结果**：首次 `finished_runs=0`，错误为 `source changed before trial launch`，trial 目录不存在；恢复后 `finished_runs=1`，该 trial 被重新执行而非复用。递归检查临时 study 内全部普通证据文件，**没有保留原错误字符串**，最后一条 trial 记录也不再有 `error`。
- **影响**：审计者无法从最终 bundle 看到先前启动失败与重试；失败可能被成功结果替代，且源码曾经漂移的事实丢失。完整 trial 内的阶段失败保留测试不能覆盖这一启动前路径。
- **修复方向（本轮不实施）**：在提交 worker / 运行核心前持久化 trial 的不可覆写启动与失败记录，resume 明确拒绝已有失败或要求新 study；至少保留所有 attempt 的追加式审计历史，不能仅按目录是否存在决定重试。不得覆写正在运行实验的旧调度器快照。

## 复现公共设置

上述两项复现使用以下设置；所有生成文件位于 `TemporaryDirectory`，测试结束自动删除，没有向源码或测试文件写入复现代码。

```python
data = generate(19, 1)
data['cases'] = data['cases'][:1]
config = {'name': 'review-fixture', 'adapter': 'fixture', 'mode': 'perfect'}
response = {
    'status': 'completed', 'returncode': 0,
    'stdout': '{"response":"{\\"answer\\":null}"}',
    'stderr': '', 'elapsed_ms': 1,
}
# study 由 importlib.util 从 scripts/run_study.py 加载。
# 执行边界使用 patch('kylin_memory_bench.runner.execute', return_value=response)。
# 每次 run_study(..., repeats=1, parallel=1)；不是正式模型实验。
```

## 已验证的契约

1. **完整 trial 复用与证据不覆写**：现有并发测试以 fixture 跑两个 repeat，生成不同 `run_id`，两份证据均通过 `verify_run`；resume 复用两轮，`run.json` 字节保持不变。静态交叉检查 `runner.py:95-100`：每轮有独立临时 private root，每个 case 独立 profile/workspace，case 内阶段串行，仅 trial 之间并发。没有发现调度器共享 case 状态的直接代码路径；未据此宣称原生 CLI 全部外部状态都隔离。
2. **拒绝 partial 与配置替换**：现有测试确认改变冻结 repeat 数被拒绝；删除 trial manifest 后拒绝 resume；用同名但不同配置、且本身通过 `verify_run` 的 trial 替换原 trial，也被拒绝。不同 data / 核心 source / scheduler 由定义字典与 trial 字段比较静态覆盖，本轮未额外注入所有变体。
3. **完成不等于记忆通过**：现有失败阶段测试真实执行合成退出码 3 的本地子进程，22 个阶段错误完整保留，resume 不重跑且保留原 `run.json`。另做单 case 合成执行失败验证：`finished_runs=1`、`stage_errors=4`、`verify_run=True`，但重算 score 的 `case.passed=None`。这是预期分层，不列为 bug。`main():206` 的成功退出只表示轮数完成且核心 source 未变，不表示无阶段错误、记忆达标或正式验收。
4. **评分与配对语义未改**：脚本调用原 `run_benchmark` / `verify_run`，未改 `score_run`；运行不完整的 case 在评分中为 inconclusive，paired 按任务配对聚合、repeat 在配对内平均，并显式保留不完整覆盖率。study 本身不计算或承诺 memory pass，也不替代后续完整比较报告。
5. **FIFO 基本路径**：现有测试用合成值，通过当前用户拥有的 0600 FIFO 发送一次 JSON；读后 FIFO 删除、writer 线程正常退出，普通文件输入被拒绝。静态确认 `read_credentials:55-62` 校验类型、属主、权限及打开后 inode/device，使用 `O_NOFOLLOW`，有 64 KiB 上限与超时；`main:200-202` 将值传入环境而不是 argv。原生 API adapter 的配置使用环境变量引用或子进程环境，不直接写入原始 API key。本轮没有读取真实环境密钥或认证文件，也没有调用原生 CLI、模型或提供商。

## 审查范围与边界

- 已交叉阅读新增脚本与当前测试，以及全部 14 个核心 Python 模块：`runner`、`adapters`、`evidence`、`privacy`、`model`、`episodes`、`scoring`、`paired`、`dataset`、`fixture`、`reporting`、`cli`、`__init__`、`__main__`。没有扩展核心改动。
- 离线执行前通过 `env -i` 清空继承环境，使用固定 PATH、`HOME=/nonexistent`、`PYTHONDONTWRITEBYTECODE=1` 与 Python `-B`，避免读取真实密钥与生成仓库缓存。既有 FIFO 测试只处理合成值；没有启动自建锁压力测试。
- 5 项 unittest 为：FIFO 一次消费；独立并发与复用；partial/冻结计划拒绝；同名不同配置证据拒绝；阶段失败保留。另有本报告两项故障注入复现与一项完成/评分分层检查。5 项通过不等于本报告 P1 已修复。
- 本轮没有做多控制器竞争、锁 inode 替换、恶意父目录链接或实时文件替换竞态的动态验证；`.study.lock` 直接打开、计划及日志控制文件未统一使用 confinement 的剩余边界不另冒充已复现结论。FIFO 的权限变更竞态、未关闭 writer 的超时边界也未追加验证。
- 没有执行 48-case 两原生智能体六轮正式实验，没有做 Linux 依赖安装、打包、远程回归、模型服务验证或正式证据验收。没有搜索或读取正式结果目录、账户目录、系统钥匙串或真实认证文件。
- 所有本轮测试进程已退出，测试命令退出码 0；FIFO writer 已 join；各自临时目录已自动清理。没有操作远程、其他进程或 Git。
- 当前会话未提供 fast-context 工具，因此语义定位退回文件清单与精确内容检索；未因此启动其他代理。

## 指纹

离线验证前后两次读取相同：

```text
core source_sha256:
009a6472cd96347aa121669cb19daebb7a59a5be367943525cdc25e102cebb30
scripts/run_study.py sha256:
f85f29c48f4a58484f7509cf8227ebf7773dbe021e7b47027fa6c37286ad4380
```

核心未被本审查改动。上面的调度器指纹仅绑定本次本地验证，不宣称等于用户正式六轮正在使用的旧快照。

## 限定收尾复核追加 · 2026-10-09

本节保留前文原始审查记录，只复核两项 P1 及其直接修复路径，不重读 14 个核心模块、不扩展指标。本轮只阅读当前 `run_study.py`、`test_study.py` 和本报告；不改源码、测试或 Git，不访问模型、远程及真实凭据。

### 收尾结论

- **P1-1 原始反例闭合**：公开接口符号链接反例通过；目录外目标保持 `unchanged\n`，不再发生追加写入。控制文件启动前经 `confined_file` 预检，实际打开经 `O_NOFOLLOW` 与文件描述符上的 regular / owner / nlink 检查。位置为新版 `scripts/run_study.py:56-65`、`126-130`、`173-174`。这些文件属性检查为静态核对，未额外开展链接竞态或所有权攻击测试。
- **P1-2 原始触发分支闭合，但失败历史契约仍有下述 P2 残留**：公开接口只读 agent 父目录反例通过；上一轮源码漂移注入也重新验证，启动前票据已留下，resume 拒绝，全部已有普通证据文件的路径与内容字节映射保持不变。修复位置为 `161-164`、`177-186`。
- **调度器绑定有效**：模块加载时保存的 `SCHEDULER_SHA256` 与当前文件一致；终态漂移检查能将 `scheduler_unchanged` 标为 false，`main:237-238` 静态确认会拒绝成功退出。动态验证只更改私有临时字节样本，并将模块 `__file__` 指向该样本，没有改真实调度器或核心文件。

### P2 残留：票据保留步骤自身失败时，仍能丢失启动失败历史

- **位置**：新版 `scripts/run_study.py:179-183`、`198-201`，恢复判断 `160-164`，最终覆盖 `209`。
- **条件**：冻结计划已存在，`.trial-claims` 不可写，且 trial 目录和对应票据均尚未创建。`claim.parent.mkdir(...)` 在留下票据前抛出权限错误，但主控仍将其当作 worker 失败写入可替换的汇总。
- **公开接口真实文件系统复现**：使用 `generate(19, 1)` 的第一个 case 和 fixture 配置，配置包含 `base_url='https://example.invalid/v1'`、`api_key_env='KMB_SYNTHETIC_KEY'`。先在合成 key 缺失时调用 `run_study(..., repeats=1, parallel=1)`，创建冻结计划后因凭据前置检查拒绝。将临时 study 的 `.trial-claims` 设为 `0500`，加入合成 key 后再次调用。该次真实权限错误发生在 `.trial-claims/review-fixture` 的创建处，没有对应 trial 或票据。随后恢复 `.trial-claims` 为 `0700`，保持同一数据、配置和输出目录再次 resume。
- **实测**：首次 `finished_runs=0`，错误为 `[Errno 13] Permission denied: .../.trial-claims/review-fixture`；恢复后 **`finished_runs=1`**。递归检查临时 study 全部普通文件，**原完整错误字符串不再保留**。这次复现不 mock `run_benchmark`、执行边界、文件系统或异常路径；实际子进程仅为本地 fixture，不访问所配置的 URL。
- **影响及定级**：原先只读 agent 父目录与源码漂移路径已获得保护；但票据设施本身出现可恢复权限故障时，仍违反不选择性重试及失败历史保留策略。由于需要票据目录自身异常，作为 **P2 残留**记录，不把已修复的原始反例继续标为未修复 P1，也不据此宣称正式六轮受影响。
- **建议（本轮不实施）**：在 worker 执行前由控制器完成票据预留；预留失败则明确拒绝研究运行/恢复，不能只写入下一次会被覆盖的汇总。或者在 resume 时同时核对不可覆写的失败账本，使无票据但已有失败记录也无法静默重试。处理应限定在调度器，不改核心评分语义。

### 本轮验证记录

1. 仅运行新增两项公开接口 unittest，**2 项通过、0 跳过，0.012 秒**：`test_event_symlink_is_rejected_before_it_can_modify_an_outside_file`（`tests/test_study.py:22-39`）；`test_failed_prelaunch_attempt_is_preserved_and_cannot_be_silently_retried`（`41-62`）。非 root 本地用户，权限故障真实生效。
2. 重放上一轮源码漂移注入，resume 返回 `prior trial attempt is incomplete; preserve history and use a new study: review-fixture/repeat-001`；票据存在，全部证据内容字节不变。
3. 复现上述票据创建失败残留，得到 `first_finished=0, second_finished=1, original_error_retained=false`。
4. 私有字节样本上的终态调度器漂移验证得到 `finished_runs=1, source_unchanged=true, scheduler_unchanged=false`。只证明漂移检测，不把完成轮数当成 memory pass。

本轮短时验证进程退出码 0，整条验证约 0.56 秒。没有运行 FIFO/锁压力测试，没有遗留测试进程；各自 `TemporaryDirectory` 已清理，临时只读权限在清理前恢复。沿用 `env -i`、`HOME=/nonexistent`、Python `-B` 和禁止字节码缓存的环境隔离；未重跑完整 study 测试集或核心回归。

本轮验证前后指纹相同：

```text
core source_sha256:
009a6472cd96347aa121669cb19daebb7a59a5be367943525cdc25e102cebb30
new local scheduler sha256 (loaded and on disk):
33f95d652d97072f5881e264bd545a2ea01356de71ae8d7a262c3acf9c5447cb
```

用户提供的旧快照私有 Git `1a40d85`、服务器仍为 `f85f29...`、新目录无 symlink 且六个 trial 均已创建/未触发重试，是本轮背景说明，未访问 Git 或服务器独立核验；本轮结论不改变旧快照、不修改运行中服务器文件，也不替代正式实验的结果审计。

## 票据预留 P2 最终闭合追加 · 2026-10-09

**结论：上一节的 P2 残留已闭合；原始启动失败反例仍被拒绝恢复。** 本轮只核对票据预留与失败历史保留，不扩大审查范围。前文问题与中间版本指纹保留为历史记录，本节是该 P2 的最新状态。

- **代码位置**：当前 `scripts/run_study.py:168-175` 在控制器中预留全部 pending claim，位于 `ThreadPoolExecutor`（`194-195`）及 worker 异常捕获（`199-202`）之前。预留错误直接传播，不进入生成失败汇总的路径；保留票据的未完成 trial 仍由 `161-164` 拒绝 resume。
- **原 P2 真实文件系统反例重放**：沿用前节单 case fixture、缺失合成 key 先建立冻结计划、`.trial-claims` 设为 `0500`、再提供合成 key 的设置。现在得到 **直接抛出的 `PermissionError`**，而非 `finished_runs=0` 的汇总返回。仅以 wraps spy 观察调用，确认 **线程池创建 0 次、`run_benchmark` 调用 0 次**；没有 trial 目录、`study.json` 或 `study-progress.json`，已有普通文件的路径/内容字节映射保持不变。权限恢复为 `0700` 后允许首次实际 trial 正常完成，没有先前被记录的 trial 失败被成功覆盖。执行过程中未 mock 权限错误、文件系统或 runner 行为。
- **原启动失败反例重放**：票据预留后注入启动前源码指纹不匹配，失败记录和 claim 均保留；同目录 resume 返回 `prior trial attempt is incomplete; preserve history and use a new study: review-fixture/repeat-001`，全部已有普通证据文件内容字节不变。没有修改真实源码。
- **针对性 unittest**：`test_claim_failure_aborts_before_any_trial_launch_or_summary_replacement`（`tests/test_study.py:22-45`）和 `test_failed_prelaunch_attempt_is_preserved_and_cannot_be_silently_retried`（`66-87`），**2 项通过、0 跳过、0.009 秒**。加上上面两个原始反例重放，整条验证约 0.18 秒、退出码 0。没有重跑完整回归或其他安全场景。

本轮前后核心与当前本地调度器指纹相同：

```text
core source_sha256:
009a6472cd96347aa121669cb19daebb7a59a5be367943525cdc25e102cebb30
current local scheduler sha256:
e7a07c993a0f2d92253d16110d93e7923bef754b30eacd13ca428e1a56f4e3bb
```

仅追加本报告，未改源码、测试、Git 或评分语义；没有读取真实凭据、访问远程/模型，实际子进程只为本地 fixture。测试沿用清空继承环境和禁用字节码缓存的隔离设置；进程已退出，临时权限已恢复，临时目录已清理。正在运行六轮使用旧冻结 `f85f29...` 是用户提供的背景，本轮没有访问、覆盖或重新认证该快照及服务器文件，也不把本地闭合结论当成正式实验结果验收。至此，本次限定审查记录的两项原始 P1 及该 P2 残留均有对应闭合证据；任务结束。
