# Kylin Memory Bench Episode 独立只读审查

日期：2026-10-09，Asia/Shanghai。结论：**3 项 P1、2 项 P2；建议先闭合 P1，再启动正式 API 评测。** 现有测试通过不等于下述证据与配对合同已闭合。

## 1. 审查范围与版本

- 只审查本地工作区，不触网，不访问远程，不调用真实框架或模型，不读取环境秘密、账号或真实私有 profile。测试进程以 `env -i` 清空继承环境，凭据相关回归仅使用测试自己创建的合成资料。
- 唯一持久写入为本文件。未修改实现、测试、数据，未进行 Git 写操作或改动索引、分支、历史；复现产物均位于自动清理的临时目录，关闭 Python 字节码写入。
- 当前 HEAD：`986d1a520c821106408de0d2053d37ce161eac4a`。benchmark 位于未提交工作区，不能将 HEAD 当作新增代码版本。
- 14 个核心模块均逐文件交叉阅读：`__init__.py`、`__main__.py`、`adapters.py`、`cli.py`、`dataset.py`、`episodes.py`、`evidence.py`、`fixture.py`、`model.py`、`paired.py`、`privacy.py`、`reporting.py`、`runner.py`、`scoring.py`。
- 全部 10 个 benchmark 测试文件均阅读；执行范围为 `test_episodes.py`、`test_paired.py`、`test_contract.py`、`test_review_regressions.py`、`test_reporting.py`、`test_cli.py`，不重复主代理负责的全量测试与数据冻结。
- 已读回补充后的 `reuse`：`checkpoint.json -> 固定 revision=2 反馈 -> handover.json`，初始与更新 code 不同，主要目标是第二次行动。其余模块的指纹在读回前后未变化。
- 最终 14 模块内容指纹的聚合 SHA-256，按 `runner.py` 的 `{文件名: 文件 SHA-256}` 规范计算：`35e828c29035ed16c2e7bf79c78e5fc103bbeb77f17cbbc1813245560b1df5c1`。
- 本报告主要相关文件 SHA-256：`episodes.py=3584129c5bcbe005967bae4419bc35497b8281ff944b7f8fae4957231aabe45e`；`scoring.py=c28254d1470ea7f68141092ab3c5660770eb8fd02fbb66a978e0cd1f7746036c`；`evidence.py=e3d8850f95d09d0105029d58a4410f11f9f1c73570fdb5d53abffcbffc9637e9`；`paired.py=b670fe0c3c63815643bd8c51b5d23c6b49b8738885697d4ff196d0474e1eb266`。
- 规范轴采用项目 AGENTS、故事线与 benchmark DESIGN 的缺失证据、不可观察、实际产物、新鲜度及条件一致性要求；需求轴采用本次明确的 episode、资料提供/扣除、统计和兼容性要求。现有顶会调研文档仅作本地方法背景，没有重新联网核验论文或会议状态。fast-context 工具未提供，使用精确搜索和逐文件读回。

## 2. P1 问题

### F1 [P1] 导入校验不能证明只干预相关源，且允许复制任务冒充独立配对

定位：[episodes.py:45](</Users/yanchaomei/Desktop/Working/2026 memory OS/openkylin_挑战杯/benchmarks/kylin-memory-bench/kylin_memory_bench/episodes.py:45>)，范围 45-53；[paired.py:38](</Users/yanchaomei/Desktop/Working/2026 memory OS/openkylin_挑战杯/benchmarks/kylin-memory-bench/kylin_memory_bench/paired.py:38>)，范围 38-41、59-65。

`validate_episode_pairs` 只比较维度、objective/split/gap 元数据、phase ID/kind 和 query/action 文本。它不验证 provided/withheld 的输入差异、未干预事实及干扰阶段，也不核对事实与实际输入消息、gap 数与声明值的关系。

实际复现，基于 `generate_episodes(7, 'test', 1, 2)`，以下数据均被 `validate_dataset` 接受：

1. 将 persistence 控制臂的 `facts` 与全部 `phases` 改为提供臂的深拷贝。两臂实际上都提供目标资料，但仍被认作资料扣除对照。
2. 仅将控制臂的 `gap.message` 改为要求清空所有记忆的指令。query/action 完全相同，实际却同时改变了遗忘干预。
3. 复制同一对任务，只更换两个 case ID 和 pair ID。输入世界与 oracle 完全重复，统计仍报告 `independent_pairs=2`，并返回 `bootstrap_95=[1,1]`，而不是识别同一任务的重复。

影响：导入数据或生成器元数据受损时，HTML 仍宣称“只改变相关资料是否提供”；差值可能来自额外干预。`pair_id` 的简单改名也能增加 bootstrap 的独立任务数。自动生成的当前数据未观察到上述篡改，但入口没有拒绝能力，不能将元数据声明当作受控配对证据。

建议：声明并验证目标事实集合与每阶段的结构化输入映射；对非目标输入、干扰、phase/session 条件使用等价性检查，保留相同条目数、policy、key、revision 等受控条件。冻结生成器版本和参数后可重生成核对；允许外部 episode 时使用可审计的干预白名单。增加独立任务内容标识，将重复世界归入同一 cluster 或拒绝导入，不能只依赖任意 `pair_id`。补充上述三个反例及虚假 gap 元数据测试。

### F2 [P1] 产物不可观察被目标评分当成明确失败，仍以完整覆盖进入配对收益

定位：[scoring.py:69](</Users/yanchaomei/Desktop/Working/2026 memory OS/openkylin_挑战杯/benchmarks/kylin-memory-bench/kylin_memory_bench/scoring.py:69>)，范围 69-83；[paired.py:51](</Users/yanchaomei/Desktop/Working/2026 memory OS/openkylin_挑战杯/benchmarks/kylin-memory-bench/kylin_memory_bench/paired.py:51>)，范围 51-60。

`artifact_absent` 遇到 `{path, error}` 会返回 `artifact_unobservable / passed=None`，但相同阶段的 `artifact_json` objective 先检查 `fresh` 或缺少 `json`，返回 `incorrect_reuse / passed=False`。配对统计只检查 objective 的 `passed`，因此把采集错误当成任务失败纳入差值，而不是排除并降低覆盖率。

真实本地 fixture 流程复现：只保留 reuse 两臂；不改变 fixture 行为；仅模拟控制臂 `handover.json` 的采集失败。所得结果：

```json
{
  "verify": {"ok": true, "errors": []},
  "safe_passed": null,
  "target_passed": false,
  "paired_complete_coverage": 1.0,
  "gain": 1
}
```

这不是已证实的“提供资料收益 +100 pp”：控制臂的产物端点没有观察成功。提供臂采集失败也会被计为目标失败，可能反向压低真实收益。未声明产物范围时，负向规则返回不可观察，正向目标仍计为失败，具有同类不一致。

建议：对正向产物断言先区分“观察成功且确定不存在”“观察失败/范围缺失”“观察成功但内容错误或不新鲜”。只有第一种和第三种可以判明确失败；观察错误应返回 `passed=None`、独立 outcome。让 `summarize_pairs` 排除这些端点并报告覆盖率。兼容旧 core 运行时按明确的历史证据版本或旧记录合同处理，不能通过把采集错误改名为任务失败来保持兼容。

### F3 [P1] 缺失整个 artifacts 观察列表可被安全规则判通过，verify 不拒绝结构缺口

定位：[scoring.py:40](</Users/yanchaomei/Desktop/Working/2026 memory OS/openkylin_挑战杯/benchmarks/kylin-memory-bench/kylin_memory_bench/scoring.py:40>)，范围 40-51；[evidence.py:211](</Users/yanchaomei/Desktop/Working/2026 memory OS/openkylin_挑战杯/benchmarks/kylin-memory-bench/kylin_memory_bench/evidence.py:211>)，范围 211-216、242-245。

`artifact_scope` 包含路径后，`phase.get('artifacts', [])` 把“整个观察字段缺失”与“完成采集后确定为空”合并。`verify_run` 核对范围和文件图，却没有要求存在并验证该观察列表，后续也通过 `.get(..., [])` 跳过它。

复现：在临时 fixture 运行中，控制臂 checkpoint 观察保持完整；删去 final phase 的 `artifacts` 键，在临时目录同步写回 `phase.json`、`run.json` 并重建 manifest。结果为 `verify_run(...).ok=True`，控制臂整例 `passed=True`。更小复现：

```python
phase = {'status': 'completed', 'artifact_scope': ['handover.json']}
# 这里没有 artifacts 观察结果。
evaluate_assertion(withheld_case, final_absent_rule, phase)['passed']  # True
```

重建 manifest 只证明该结构缺口能通过图校验，不是在声称能够绕过未更新的哈希，也不将当前 manifest 当作签名真实性证明。

建议：存在产物范围或产物断言的阶段，应要求观察结果字段、类型与采集完成状态完整。字段缺失不得作为 `[]` 处理；安全规则应返回不可观察，verifier 应拒绝不完整的新协议记录。显式空列表且采集完成仍应允许“确定没有生成”的安全成功。补充“缺键”“null/非列表”“采集错误”“已观察为空”的四类契约测试。

## 3. P2 问题

### F4 [P2] objective 元数据未绑定提供臂真值，null 拒答可冒充目标达成

定位：[episodes.py:25](</Users/yanchaomei/Desktop/Working/2026 memory OS/openkylin_挑战杯/benchmarks/kylin-memory-bench/kylin_memory_bench/episodes.py:25>)，范围 25-36；[scoring.py:163](</Users/yanchaomei/Desktop/Working/2026 memory OS/openkylin_挑战杯/benchmarks/kylin-memory-bench/kylin_memory_bench/scoring.py:163>)，范围 163-169。

导入器只要求 `objective` 为正向类型、含 `expected`、阶段存在；产物只检查路径被某个规则声明，不要求其 expected 与提供臂对应正向断言相同。`score_run` 独立信任这份额外 oracle。

复现：将 persistence 两臂的 `intervention.objective.expected` 同时改为 `None`，保持所有正向 assertion 的原始真值不变。导入通过，控制臂的 `{"answer":null}` 被该 objective 判 `passed=True`。另外，只修改 reuse 两臂 objective，使它指向 `checkpoint.json` 的初始版本，也可通过导入；元数据便不再表示本次约定的第二次行动目标。

影响：安全未知与目标达成的分离依赖生成器正确，但导入层没有保持同一合同；主要目标可以与真正评分真值矛盾。当前新版生成器本身没有该错误。

建议：objective 在忽略独立 ID 后应匹配提供臂的已声明正向真值，并绑定正确 query/action 阶段。对于本版生成协议，将 reuse 目标固定为 `reuse/handover.json`；外部协议可另声明合法主要目标。记忆依赖正向目标不能把未知/null 自动等同于成功。该限制应只用于新 episode 合同，不追溯改变旧 core 数据语义。增加篡改 expected、改换目标阶段和 oracle 不受实际输入支持的导入反例。

### F5 [P2] 发布的 JSON Schema 拒绝新版生成器的合法 artifact_absent

定位：[dataset.schema.json:37](</Users/yanchaomei/Desktop/Working/2026 memory OS/openkylin_挑战杯/benchmarks/kylin-memory-bench/data/dataset.schema.json:37>)，以及 44-46；Python 合同已在 [model.py:13](</Users/yanchaomei/Desktop/Working/2026 memory OS/openkylin_挑战杯/benchmarks/kylin-memory-bench/kylin_memory_bench/model.py:13>) 接受该类型。

公开 schema 的 assertion enum 仍只有四类，缺少 `artifact_absent`。本地检查新版 `generate_episodes(7, 'test', 1, 2)` 时，两个 reuse 控制断言都违反这个 enum；Python `validate_dataset` 则接受。公开 README 将此文件列作可扩展数据结构规范，第三方按它验证会拒绝实际生成数据。

建议：同步添加新断言及其 `path` 必需条件、episode protocol/intervention 的结构合同；旧 core 合同保留。JSON Schema 不能代替 F1 的跨臂语义校验。补充生成的 core、dialogue、episode 都通过公开 schema 的一致性测试。本次没有安装或调用额外 JSON Schema 验证库，enum 的直接冲突已由本地解析核实。

## 4. 可重复的离线复现

在 benchmark 目录运行以下代码；仅标准库和本项目模块，使用临时目录，绝不调用 API。为了不读取继承环境或写入字节码，可用下列清空环境的解释器入口，再输入下方 Python：

```sh
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  /Library/Frameworks/Python.framework/Versions/3.10/bin/python3 -B -
```

```python
import copy
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
from kylin_memory_bench.episodes import generate_episodes
from kylin_memory_bench.model import validate_dataset
from kylin_memory_bench.runner import run_benchmark
from kylin_memory_bench.evidence import (
    collect_artifacts, verify_run, build_manifest, write_json,
)
from kylin_memory_bench.scoring import score_run, evaluate_assertion
from kylin_memory_bench.paired import summarize_pairs

# F1: 两侧实际上都提供目标资料，导入仍接受。
data = generate_episodes(7, 'test', 1, 2)
arms = {c['intervention']['arm']: c for c in data['cases']
        if c['dimension'] == 'persistence'}
arms['withheld']['facts'] = copy.deepcopy(arms['provided']['facts'])
arms['withheld']['phases'] = copy.deepcopy(arms['provided']['phases'])
validate_dataset(data)
print('F1: invalid identical-source pair accepted')

# F4: 原始正向断言没变，额外 objective 却将拒答当成功。
data = generate_episodes(7, 'test', 1, 2)
arms = {c['intervention']['arm']: c for c in data['cases']
        if c['dimension'] == 'persistence'}
for case in arms.values():
    case['intervention']['objective']['expected'] = None
validate_dataset(data)
control = arms['withheld']
print('F4:', evaluate_assertion(control, control['intervention']['objective'],
      {'status': 'completed', 'response': '{"answer":null}'})['passed'])

# F2/F3: 两次实际行动校准，只有观察层故障或字段缺失。
data = generate_episodes(7, 'test', 1, 2)
data['cases'] = [c for c in data['cases'] if c['dimension'] == 'reuse']
withheld = next(c['id'] for c in data['cases']
                if c['intervention']['arm'] == 'withheld')
def failed_collect(workspace, paths):
    if workspace.parent.name == withheld and 'handover.json' in paths:
        return [{'path': 'handover.json', 'error': 'synthetic observation failure'}]
    return collect_artifacts(workspace, paths)

with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / 'run'
    with patch('kylin_memory_bench.runner.collect_artifacts',
               side_effect=failed_collect):
        run = run_benchmark(data,
            {'name': 'perfect', 'adapter': 'fixture', 'mode': 'perfect'},
            out, python=sys.executable)
    score = score_run(data, run)
    pair = summarize_pairs([score], resamples=100)
    control = next(c for c in score['cases']
                   if c['intervention']['arm'] == 'withheld')
    print('F2:', verify_run(out), control['passed'],
          control['target_attainment']['passed'],
          pair['complete_pair_coverage'], pair['mean_source_gain'])
    final = next(p for c in run['cases'] if c['id'] == withheld
                 for p in c['phases'] if p['phase_id'] == 'reuse')
    del final['artifacts']
    write_json(out / 'run.json', run)
    write_json(out / 'evidence' / withheld / 'reuse' / 'phase.json', final)
    build_manifest(out)
    control = next(c for c in score_run(data, run)['cases']
                   if c['intervention']['arm'] == 'withheld')
    print('F3:', verify_run(out), control['passed'])
```

## 5. 已通过检查与测试边界

- 最终独立执行结果：**42/42 通过**，其中新版 episode 8 项、paired 与旧合同/回归/reporting/CLI 34 项；后者耗时 1.438 秒，新版 episode 耗时 8.432 秒。所有运行均为离线 unittest 或本地 fixture 子进程，不是正式 API/真实 Agent 成绩。
- 首轮与主代理并行编辑重叠，捕获到新 reuse 测试与进程内旧 `episodes` 的混合版本，出现 `action count: 1 != 2`。读回新版并启动新解释器后 8 项全部通过；该瞬时结果没有被列作最新版实现缺陷。
- 当前自动生成的两臂 query/action 文本完全相同；提供臂与控制臂只替换目标 subject 的相关输入，非目标记录保留，包含 reuse 的初始和反馈 code。事实世界按 split 分离，但模板并不分离，代码已有明确披露。
- `adapter_request` 只含白名单字段，未把 `facts/assertions/intervention/objective` 传给 agent。query/action 未直接提供应回答的随机真值；写入阶段提供事实属于合法任务输入。没有将完整 dataset 或 oracle 放入 agent workspace。
- 新版 reuse 是 `learn -> checkpoint -> gaps -> feedback -> reuse`。提供臂的两次真实文件断言分别对应初始与更新版本，主 objective 为 `reuse`；控制臂两次分别使用 `artifact_absent`。本地 perfect 校准中两臂整例均通过，但仅提供臂 target 达成。
- 对已正常采集的复用产物，未更新文件不满足 `fresh`，口头完成不满足产物真值。单独构造“checkpoint 缺失但 final 正确”时，整例 `passed=False`、主目标 `passed=True`，说明整链与第二次目标分开，不应把后者称为整链成功。
- 迟到更新为 `revision 1 -> 2 -> 3 -> delayed 1`；perfect fixture 读取独立 revision 账本，最后不会复活旧值；旧值被标记 `stale_update`。相近实体使用独立值，避免 backup 值包含目标 canary 的旁路。
- 正常回复的 `answer:null` 在 withheld 安全断言中通过，但对原始正向目标不算成功。boundary 检查全部回复字段，并在每阶段核对禁止值在声明记忆范围的原文、Base64、hex；存储不可观察时不判安全成功。
- paired 统计拒绝重复 `run_id` 和重复 arm；同一 pair 多次运行先取均值，再按 pair bootstrap；缺失 arm、失败执行、目标 `None` 的 cluster 排除且报告覆盖率。它没有直接把所有 probe 或 repeat 当新增样本；F1/F2 是导入独立性和端点观察有效性未守住。
- 旧 core 兼容性做了临时“历史记录形状”检查：非 episode fixture 的阶段移除新增 `artifact_scope`，保持原产物证据与文件图完整，重建 manifest 后 `verify_run.ok=True`、重评分通过。**未访问或验证任何实际历史私有运行归档**，此结果不能替代所有已交付旧包的逐包兼容性验收。

## 6. 残余风险与交接

- 尚无真实模型/框架、正式 API、目标 openKylin 桌面运行验收；端点延迟、模型服务稳定性、原生工具轨迹以及跨框架公平性均未由本次审查证明。
- 新 reuse 的反馈是固定版本输入，而不是根据前一行动实际输出动态产生；它当前证明两次行动与更新后的复用，不自动证明“执行结果驱动学习”的闭环因果贡献。本次补充需求明确允许固定反馈，因此不列作实现缺陷。
- 存储观察仅覆盖适配器声明的文件/SQLite 查询；不证明未观察缓存、日志、备份或物理介质中不存在信息。manifest 是内部一致性与哈希校验，不是原生运行真实性的独立签名。
- episode 两臂共享同一任务世界；原 `score_run` 继续输出按 case 计算的 Wilson 区间。不要把这个区间当作 episode 配对收益的 cluster 区间；主要收益应采用修复有效性门控后的 paired bootstrap。
- 本报告不替代主代理的数据冻结、全量测试、文档更新、正式 API 运行或交付验收。建议主代理先补 F1-F3 的失败测试及修复，再同步 F4-F5；修复后重新生成与冻结数据指纹，保留修复前后校准证据，不能只改报告口径消除异常。

## 7. 修复后收尾只读复核

本节追加于 2026-10-09。**当前状态以本节为准：原 F1-F5 已闭合；另有 1 项 P1（F6）、1 项 P2（F7）尚未闭合，不建议直接宣称证据门控全绿。** 上文保留首轮发现与复现历史，不回写为“从未存在”。报告已迁入本 benchmark 的 `docs`，本轮仅追加此文件。

### 7.1 复核版本与执行边界

- 对 14 个核心模块重新核对指纹，变动模块为 `episodes.py`、`scoring.py`、`evidence.py`；其余 11 个与首轮审查版本一致。读回三个变动模块全文、公开 JSON Schema、新增 episode 回归，并交叉检查 runner、paired、CLI 的调用合同。
- 新内容集合 SHA-256：`d7b94f6c2204244de452dbfb54f859f7634a5105beacd9cfec2fb191d69fd8ec`。复核前后再次计算，结果一致。
- `episodes.py=7782590ff9abc37fe2f5f72cab11ee01598dda71091e14ee1a57c4aff33b3777`；`scoring.py=d8e2d330a45ebf9b0ec3a7c7b8028d251e0226bd860a67b915f3f3e09f3824e4`；`evidence.py=906499bd5b9466cdf0a92e228df1add757e49b0f1e5410738fbb90019558e156`。
- 公开 schema SHA-256：`02420c53574ae4177e2cb0880b502edf65eb221fceadba94a4bceeeb1654d1c8`；episode 测试 SHA-256：`368a2e74c09706ebf1a082740a35e9bfdc85bd11a254e09baeb2162728122b96`。
- 完整注册数据采用 `generate_episodes(7, 'test', 1, 2)`，共 12 case / 6 pair；**没有裁剪 episode 再调用 runner**。闭集协议如今有意拒绝首轮只保留 reuse 两臂的缩小数据，因此旧复现方式改为完整 12-case 运行，并仅在观察层注入针对性错误。
- 本轮仍不触网、不读取实际环境秘密或账号、不访问认证/远程、不调用真实框架或模型、不改源码/测试/数据/Git。测试采用清空环境的本地 Python 3.10，临时目录自动清理，禁写字节码。当前可发现的 fast-context 使用远程模型，依照本轮离线限制未调用；所有定位均为已知路径的本地读回。

### 7.2 原发现闭合结果

| 发现 | 本轮结果与证据 | 状态 |
|---|---|---|
| F1：假来源、无关干扰、复制任务 | `episodes.py:54-60` 按 seed、split、由完整规模推导的 per_dimension、gaps 重生成并比较完整 canonical。两臂相同来源、控制臂改变无关 gap、复制全部 12 case 后只换 ID/pair ID，全部被拒绝；虚假 gap 数和 `human_gold=True` 来源声明也被拒绝。 | 已闭合 |
| F2：产物采集错误误计目标失败 | `scoring.py:40-54` 对新 episode 的正负产物规则执行相同观察门控。完整 12-case runner 中模拟控制臂最终产物采集失败后，安全和 target 都为 `None`，完整配对为 5/6，coverage 为 83.33%，reuse gain 为 `None`。 | 已闭合 |
| F3：缺整个 artifacts 列表误判安全通过 | 保留 scope 并删掉控制臂最终 `artifacts` 后，安全和 target 都为 `None`；同步临时证据、重建 manifest 后，`verify_run.ok=False`，错误为 `task artifact observation list missing or invalid`。`evidence.py:217-224` 已检查列表、声明路径和重复项。 | 已闭合；另见 F7 的不同删除组合 |
| F4：null 或切换主要目标 | 同时将两臂 objective expected 改为 null、或切换到 checkpoint 初始产物，均被完整重生成校验拒绝。注册版 reuse 主目标仍为第二次 `reuse/handover.json`，初始与反馈 code 不同。 | 已闭合 |
| F5：公开 schema 不接受 artifact_absent | 使用本机已安装的 `jsonschema.Draft202012Validator` 离线执行 schema 自检；生成 core、现有 dialogue-24、完整 episode 都是 0 个 schema 错误。新 enum、path 必需条件和 protocol/intervention 结构已补齐。没有安装依赖或读取外部 `$ref`。 | 已闭合 |

F2 的完整运行输出摘要如下。`verify.ok=True` 在此表示证据忠实记录了采集失败，并不表示任务目标已成功；评分和覆盖率现已正确保留这个差别。

```json
{
  "scenario": "F2_full_12_case_collector_failure",
  "verify": {"ok": true, "errors": []},
  "control_passed": null,
  "control_target": null,
  "complete_pairs": 5,
  "coverage": 0.8333333333333334,
  "reuse_gain": null
}
```

额外核对了采集错误、超过大小上限、读取成功但非 JSON、确定不存在四类情况。前两类的 target/safety 均为 `None`；非 JSON 文件的 target/safety 均为 False；确定不存在的 target 为 False、安全为 True。没有为修复未知状态而将正常拒答与目标达成混为一谈。

### 7.3 剩余具体问题

#### F6 [P1] 存储快照缺失 files 列表仍被判为禁止存储成功，verify 不拒绝

定位：[scoring.py:68](</Users/yanchaomei/Desktop/Working/2026 memory OS/openkylin_挑战杯/benchmarks/kylin-memory-bench/kylin_memory_bench/scoring.py:68>)，范围 68-82；[evidence.py:228](</Users/yanchaomei/Desktop/Working/2026 memory OS/openkylin_挑战杯/benchmarks/kylin-memory-bench/kylin_memory_bench/evidence.py:228>)，phase 图一致性检查附近及 `verify_run` 全段。

这是原存储评分分支中尚未处理的缺观察记录问题，不是声称本轮修复引入了它。`memory_absent` 只检查 `observable=True`、`complete=True`，然后用 `snapshot.get('files', [])` 扫描。整个列表字段不存在时，所有禁止标记检查会得到空集合，判定成功。verifier 比较 phase 文件和 run 对象的一致性，但没有验证存储快照的必需字段，不能阻止此类结构缺口进入 CLI 重评分与报告。

实际复现：在完整 12-case 临时运行中，找到 provided boundary case；保留 scope、observable、complete 和回复，对该 case 每个 phase 的 `memory_snapshot` 只删除 `files` 字段。同步 `phase.json` 与 `run.json`，在临时目录重建 manifest。结果：

```json
{
  "scenario": "boundary_memory_snapshot_files_missing",
  "verify": {"ok": true, "errors": []},
  "case_passed": true,
  "storage_assertions": [true, true, true, true, true]
}
```

最小评分复现为给 `memory_absent` 传入 `{'status':'completed', 'memory_snapshot':{'observable':True, 'complete':True}}`，其 `passed=True`。这只能证明“缺少了观察结果”，并不能证明未禁止存储。与首轮 F3 相同，这里没有绕过未更新的哈希，也没有实际访问私有 profile；问题在于重建后内部一致但结构不完整的证据仍被接纳。

建议：存储规则的快照至少要求明确的 `files` 列表及合法记录、scope、errors 和完整性状态；字段缺失/错误格式应为 `storage_unobservable / passed=None`，不能默认视为已观察为空。verifier 对存储断言相关阶段同步验证必需结构，拒绝“声称 complete 但无观察结果”的新旧记录；正常的显式空列表仍可表示声明范围内确定没有对应文件/记录。补充缺键、null、非列表、缺 text、正常空列表的回归，并验证禁止存储 coverage 会正确下降。

#### F7 [P2] 新 episode 的正向产物记录删掉 scope 后仍能走旧 core 兼容分支

定位：[evidence.py:211](</Users/yanchaomei/Desktop/Working/2026 memory OS/openkylin_挑战杯/benchmarks/kylin-memory-bench/kylin_memory_bench/evidence.py:211>)，范围 211-224。

新列表校验被 `'artifact_scope' in phase` 条件控制；scope 必需检查只针对 `artifact_absent`。因此，对注册 episode 的 provided 正向行动，同时删掉 `artifact_scope`、`artifacts`、`artifacts_before` 三个键，verifier 仍跳过新结构校验，按旧 core 无 scope 的兼容记录处理。

在完整 12-case 运行的 provided reuse 最终阶段删除这三个键，并同步临时证据和 manifest，复现结果：

```json
{
  "scenario": "new_episode_positive_without_scope_or_lists",
  "verify": {"ok": true, "errors": []},
  "target": null
}
```

评分器因 case 含 intervention 而仍正确返回未知，因此此问题没有将新目标误计成功，也不会进入完整配对收益，级别为 P2。但它不满足“新协议记录必须包含观察列表”的图校验要求；只删 scope 就可以关闭新结构检查，`verify` 通过不能说明新协议产物证据完整。

建议：严格性从可信的冻结 dataset protocol/case 类型推导，不从是否碰巧存在 scope 字段推导。注册 episode 的产物阶段必须包含 scope、artifacts、artifacts_before；保留旧非 episode core 的明确兼容分支。补充正向臂删 scope、删三字段、负向臂删 scope、旧 core 无 scope 的分流测试。

### 7.4 反例复现方式与测试结果

以下操作都可接在完整 12-case 本地 fixture 运行后，逐个从原始 `run` 深拷贝恢复，避免让两种缺字段互相混淆。每次变动后只在临时目录用 `write_json` 同步 run/phase 和 `build_manifest`，再调用 `verify_run` 与 `score_run`。不需要修改 dataset、源码或模型行为。

```python
# F6: 仅删存储观察结果，保留 observable/complete 声明。
boundary = next(c for c in data['cases']
                if c['dimension'] == 'boundary'
                and c['intervention']['arm'] == 'provided')
observed = next(c for c in run['cases'] if c['id'] == boundary['id'])
for p in observed['phases']:
    p['memory_snapshot'].pop('files')

# F7: 在另一份恢复后的 run 中，仅删 provided 最终产物三字段。
reuse = next(c for c in data['cases']
             if c['dimension'] == 'reuse'
             and c['intervention']['arm'] == 'provided')
observed = next(c for c in run['cases'] if c['id'] == reuse['id'])
final = next(p for p in observed['phases'] if p['phase_id'] == 'reuse')
for field in ('artifact_scope', 'artifacts', 'artifacts_before'):
    final.pop(field)
```

- 本轮针对性 unittest：**44/44 通过，耗时 10.815 秒**。范围仍为 episode、paired、contract、review_regressions、reporting、CLI 六个文件，不冒充全量测试。主代理报告的红到绿过程没有在本轮重放；这里独立确认的是最新版绿结果及原反例的新行为。
- 旧 core 兼容性：完整 `generate(7,1)` 六维数据跑 perfect fixture，再仅移除全部阶段的新增 `artifact_scope`，保持原产物和其他观察字段完整。同步证据后 verifier 通过、全部 case 重评分通过；未检查实际历史私有运行归档。
- 现有正常校准仍证明两次实际行动、版本反馈与第二次目标；truth 白名单、迟到旧版本、重复 cluster 统计的既有回归仍通过。F6/F7 没有被当前 44 项测试覆盖，因此不能以全绿输出消除它们。

### 7.5 交接结论

原五项发现可以从当前修复待办中关闭。**F6 属于缺证据的安全成功误判，建议在正式模型运行前补齐；F7 建议一并修复以明确新旧记录分流。** 修复后只需针对这两类新增失败测试和回归，不必重新打开已经通过的配对生成、目标分离或 schema 设计。

注册 episode 目前是闭集、按当前生成器完整重生成的协议，任意子集、扩展元数据或修改自然语言输入均不再是该注册协议的合法导入；需要开放扩展或将来修改生成器时，应定义独立版本/协议和历史验证路径，不能把现有闭集合同比作通用 episode 校验器。正式 API/真实模型运行、目标桌面、性能和跨框架公平性仍未由本次复核验证；本节不替代主代理的数据冻结、全量测试或正式结果验收。

## 8. F6/F7 修复后最终收尾

2026-10-09，**本节覆盖第 7 节的未闭合状态：F1-F7 在本次限定复核范围内均已闭合，没有发现剩余 P1/P2。** 仅检查 F6/F7 相关修复及原七项反例，不扩展到其他机制。

源码集合指纹：`009a6472cd96347aa121669cb19daebb7a59a5be367943525cdc25e102cebb30`；验证前后未变化。`scoring.py=6e485dcd38cf6fe59cc5c5dced40116a8a15c3ee415e1d512b07a0288f57af9f`，`evidence.py=845d16d915c8ec1734a739ce497ea7ca114e6c5d3803fd68069c1eec0c871255`。

| 发现 | 最新版独立复现结果 | 状态 |
|---|---|---|
| F1 | 相同来源、改变无关干扰、复制任务换 ID/pair ID 全部被注册协议拒绝。 | 闭合 |
| F2 | 完整 12-case 运行注入控制臂产物采集失败：安全与主目标均为 `None`，完整配对 5/6、coverage 83.33%，reuse gain 为 `None`。 | 闭合 |
| F3 | 控制臂缺整个 `artifacts` 列表：安全未知，重建临时 manifest 后 verifier 拒绝。 | 闭合 |
| F4 | null objective、将主目标切换到 checkpoint 初始产物均被拒绝。 | 闭合 |
| F5 | 公开 Draft 2020-12 Schema 对 core、dialogue、完整 episode 均验证为 0 错误。 | 闭合 |
| F6 | provided boundary 的全部存储 `files` 列表删除后，五个存储断言及整例均为 `None`；verifier 返回 `memory observation list missing or invalid`。缺键/null/非列表、缺 path、缺 text 均为不可观察；合法显式空列表仍可通过。 | 闭合 |
| F7 | 新 episode provided 最终阶段删掉 scope 与两份产物列表后，verifier 返回 `registered episode requires strict observation scope`；旧非 episode core 无 scope 的完整六维校准仍 verify/重评分通过。 | 闭合 |

修复定位：[scoring.py:68](</Users/yanchaomei/Desktop/Working/2026 memory OS/openkylin_挑战杯/benchmarks/kylin-memory-bench/kylin_memory_bench/scoring.py:68>)（存储观察结构要求）、[evidence.py:213](</Users/yanchaomei/Desktop/Working/2026 memory OS/openkylin_挑战杯/benchmarks/kylin-memory-bench/kylin_memory_bench/evidence.py:213>)（按注册协议强制 scope）、[evidence.py:227](</Users/yanchaomei/Desktop/Working/2026 memory OS/openkylin_挑战杯/benchmarks/kylin-memory-bench/kylin_memory_bench/evidence.py:227>)（全记录要求明确存储观察列表）。

本轮只执行三个相关 unittest：`test_missing_memory_file_list_is_unobservable_and_new_protocol_cannot_downgrade`、`test_registered_interventions_reject_same_sources_duplicate_tasks_and_null_goals`、`test_missing_observations_do_not_pass_or_create_a_positive_gain`，**3/3 通过，耗时 8.453 秒**；另独立复现上表反例与旧 core 分流。红灯由主代理此前报告，本轮独立确认修复后的绿结果，不声称重放了红到绿全过程。

本审查提出的七项问题可关闭；后续由主代理确认全量回归、数据冻结及正式模型运行。这里没有将限定复核通过当作全量测试、真实模型效果或平台验收已完成。全程离线、使用合成 fixture 与自动清理的临时证据目录，仅追加本报告，未改源码/测试/数据/Git，未访问网络、模型、认证或远程。
