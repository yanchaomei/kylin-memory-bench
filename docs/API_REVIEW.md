# 真实 API 评测只读复核

复核日期：2026-10-04；运行日期：2026-10-03。范围：`configs/real-api.json`、全部 12 个核心 Python 模块、开始复核时的 7 个既有测试文件，以及下列两份已完成记录。未读取认证文件或环境变量值，未执行原生 CLI、网络请求或模型调用；仅新增本报告。

- `O` = `results/real-api-openclaw-v2-20261003/repeat-001`
- `H` = `results/real-api-hermes-v2-20261003/repeat-001`
- 以下证据位置相对于 Benchmark 根目录，单列的核心 Python 文件名均指 `kylin_memory_bench/` 下同名文件；`~/.hermes/hermes-agent/` 仅指本机安装的 CLI 源码，不指认证目录内容。

## 问题与建议

1. **[P1，必须修复] 公网 API 使用明文 HTTP。** 两端 `base_url` 均为公网 IP 的 `http://.../v1`，适配器直接交给 provider 使用，没有 HTTPS 配置或已验证加密隧道的证据。凭据和请求内容存在传输暴露风险；日志脱敏不能保护传输链路。建议后续真实运行使用证书校验的 HTTPS，或已验证的加密隧道加本地回环入口。本次没有抓包，不能断言泄漏已经发生。证据：`configs/real-api.json:7,16`；`kylin_memory_bench/adapters.py:115-120,141-144`。

2. **[P2，建议修改] Hermes 的有效模型路由缺少运行时证明。** 两端相同的模型名、端点和 Responses 配置成立；Hermes 实际 argv 也含 `--model gpt-6-sol`。但其 `native_metadata` 仅保存会话 ID，SQLite 轨迹只导出消息，未归档实际 model/provider/base URL/API mode 或服务端请求标识。因此可确认“配置为同一请求模型”，不能仅凭这些记录证明两端最终落到同一上游模型实例。建议补充不含凭据的有效路由元数据、服务端请求标识和 CLI 源码/安装包指纹。证据：`H/evidence/persistence-0000/learn/process.json:10-11`；`H/evidence/boundary-0000/probe/phase.json:9-10,38-49`；`kylin_memory_bench/adapters.py:35,196-198`。

3. **[P2，建议修改] 同模型不等于同推理设置。** OpenClaw 明确传 `--thinking off`；Hermes 配置未指定 reasoning effort。本机 Hermes CLI 从配置读取 effort，空值返回默认，Responses 请求构造默认为启用 `medium`。这是当前安装源码支持的推导，不是历史请求抓包事实。建议显式统一或披露两端推理预算，避免把端到端耗时差异归因于记忆实现。证据：`kylin_memory_bench/adapters.py:137-143,209`；`~/.hermes/hermes-agent/cli.py:1742-1744`；`~/.hermes/hermes-agent/hermes_constants.py:143-158`；`~/.hermes/hermes-agent/run_agent.py:5978-6008`。本机 CLI 源码不在归档 Benchmark 源码指纹中。

4. **[P2，建议修改] 边界错误分类过粗，失败判定本身正确。** 两端各 4 个边界 probe 均返回对应“已批准”相近实体的值，而非 `null`；没有返回受禁 canary，每端 16 次、共 32 次边界长期记忆快照也均未命中该 canary。现有 `incorrect_reuse` 同时覆盖真实泄漏和不应回答时回答，reason 已注明这两种可能，但缺少细分。建议增加“受禁值泄漏 / 相近实体混淆 / 未知值猜测”等子原因；本轮应解释为相近实体混淆导致拒答失败，不能解释为敏感信息泄漏或禁止项持久化。证据：`kylin_memory_bench/scoring.py:73-88`；`kylin_memory_bench/dataset.py:85-100`；两端 `score.json:728-762,874-908,1020-1054,1166-1200`；`O/evidence/boundary-0000/probe/phase.json:8,171,188`；`H/evidence/boundary-0000/probe/phase.json:8,27,49`。

## 已确认事实

| 检查项 | 确认结果与证据 |
|---|---|
| 原生 CLI 与模型配置 | 两端实际命令分别为 `openclaw agent --local --json` 与 `hermes chat -Q -q`，不是 fixture；同为 `gpt-6-sol`、同端点、同凭据变量名、Responses 模式。OpenClaw 全部 88 阶段元数据与 130 条 assistant 轨迹消息均声明 `gpt-6-sol`。见 `configs/real-api.json:4-19`、`O/evidence/persistence-0000/learn/stdout.txt:10-13`、`H/evidence/persistence-0000/learn/process.json:3-15`；Hermes 的证明边界见问题 2。 |
| 会话复用修复 | OpenClaw 每阶段只删除私有 profile 的 `agents/main/sessions`，不会删除 workspace 的 `MEMORY.md` 或 `memory/*.md`。Hermes 不删除 `state.db`，也不传 resume 参数，通过新会话隔离旧消息。两端各 88 个请求 ID、88 个原生会话 ID 均唯一，每阶段轨迹只有当前一条 user 消息；非 update 案例的长期记忆文件路径与摘要逐阶段不变。见 `adapters.py:123-129,159,182-187,210-214`、`runner.py:100,111-130`、`tests/test_adapters.py:65-70`；两端 `evidence/persistence-0000/{learn,gap,probe1,probe2}/phase.json`。删除聊天目录不是缓存清除或完整遗忘证明。 |
| Hermes 标题行解析 | 只移除开头精确的已知 `╭─ ⚕[可选 VS16] Hermes ─+╮` 整行一次，并要求结尾有合法 `session_id`。不在日志中搜取任意 JSON；warning、近似标题、第二个标题均保留并使 answer 解析失败，尾部额外垃圾被拒绝。本轮 84 阶段有已知标题、4 阶段无标题，全部可按当前协议解析。见 `adapters.py:27-35`、`scoring.py:11-21`、`tests/test_adapters.py:11-22`、`H/evidence/persistence-0000/learn/stdout.txt:1-5`。 |
| 长期存储与任务产物 | 观察范围仅为两端声明的记忆文件，不将会话轨迹冒充长期库；两端各 4 个任务复用案例均有当前阶段新建/更新且内容正确的真实文件。见 `adapters.py:129,159`、`runner.py:115-140`、`scoring.py:40-70`、两端 `evidence/reuse-0000/reuse/phase.json`。 |
| 完整性与评分 | 两端 `verify_run` 均通过，分别校验 531 个清单文件、阶段关联、独立会话、stdout 解析与产物新鲜度。当前全部 12 个模块的摘要匹配归档；共同源码指纹为 `b632167a2d459ad283265cd257136b00b023d2ea16a7163442fdfd09287be814`。复算断言、分类、六维指标均匹配；仅累计毫秒的浮点求和尾差小于 `1e-6 ms`，不是结果变化。见 `evidence.py:143-249`、`O/run.json:43`、`H/run.json:44`、两端 `manifest.json` 与 `score.json`。 |
| 凭据与隐私 | 两份清单仅含 dataset/run/score 及阶段六类证据文件，没有认证文件或环境值转储；扫描 1,062 个清单文件，未命中常见 provider key、Authorization 字面量、私钥、邮箱或用户 home 路径。凭据变量名不是凭据值；`KMB_FAKE_*` 是合成 canary，在 learn 请求/轨迹中出现属预期。API 分支不复制真实认证或个人记忆，公开日志按已知 secret 脱敏。见 `runner.py:94-106,118-150`、`adapters.py:84-98,130-159`、`privacy.py:20-33`。扫描不等于对未知凭据格式或真实环境值的穷尽证明；传输风险另见问题 1。 |

## 本轮结果与边界

| Agent | 完成案例/阶段 | 保持、调用、更新、区分、复用 | 边界 | 可评分覆盖率 |
|---|---:|---|---:|---:|
| OpenClaw 2026.3.8 (3caab92) | 24 / 88 | 每维 4/4 | 0/4 | 每维 100% |
| Hermes v0.8.0 (2026.4.8) | 24 / 88 | 每维 4/4 | 0/4 | 每维 100% |

每端均为 48 条断言 `correct`、4 条 `incorrect_reuse`；全部阶段 `completed`，本轮没有 runtime/protocol error 被算成记忆遗漏。边界四层的声明长期文件均未出现受禁标记，允许保留对照均成功，但不能正确拒答相近的未获准实体。`memory_absent` 通过仅覆盖声明范围，不证明会话日志、缓存、外部副本或整个系统无残留。

两端使用同一 24 案例合成数据，指纹 `0a99c389dda274ad72ed59aa6da792729c3a61aa3d57ea131d7cc6be5bbbc41c`；每端本次仅复核 1 轮，不是 48 个不同案例，也不是 600 条扩展集成绩。归档环境是 Darwin arm64，`openkylin=false`，不能作为 openKylin 验收。阶段 P95 分别约 19.473 s、24.922 s，含模型、工具及进程启动，不是端侧检索延迟。证据：`O/run.json:18-28,17992`、`H/run.json:19-29,6125`；两端 `score.json:65-100`。

## 本次验证

- 29 项纯逻辑 unittest 全部通过：全部 ContractTests、PrivacyTests，及适配器解析、边界扫描、产物判定、重复条件、报告比较的选定用例。另以合成文本核对已知标题、warning、近似标题、双标题、尾部垃圾 5 类解析情形。
- 使用 `python3 -B` 只读核验与内存复算；未实例化 Adapter、未运行会读取环境/认证或写文件的完整测试套件，未重新跑真实评测。报告不能替代新一轮模型调用、三轮稳定性或目标平台验收。

**结论：** 原生 CLI 执行、会话隔离、长期记忆保留、严格标题行处理和现有分数均有可核对证据；当前结果可作为受控合成数据上的真实 CLI 单轮记录。正式对外比较前，应修复明文传输，并补齐 Hermes 有效路由、推理设置和边界失败子分类的证据/表述。

## 2026-10-04 修复跟踪

本节由实现者追加，原只读复核内容原样保留。

| 项目 | 本轮处理 |
|---|---|
| 公网明文传输 | 当前配置改为 `https://api.adslab.icu/v1`，默认证书校验通过并实际完成 `gpt-6-sol` Responses 生成；自然语言运行使用新入口，旧记录不改写 |
| Hermes 原生模型记录 | 工具轨迹增加当前会话的 `model/input_tokens/output_tokens/reasoning_tokens` 只读查询，不导出认证或 `model_config`；回归验证值与秘密字段隔离 |
| 推理设置 | 配置显式共同指定 `off`，映射为 OpenClaw `--thinking off` 与 Hermes `agent.reasoning_effort=none`；另支持双方共同 `low/medium/high`；实际服务端用量仍单独记录 |
| 边界失败解释 | 测试报告已将禁止项持久化检查、禁止值回复检查和未知项目错误关联分开说明；历史得分与机器分类不修改 |
| 验证 | 本地及 Linux 分别 71 项完整 unittest 通过，包含新适配器回归和 18 项自然语言数据测试 |

原生模型字段可以证明框架使用的模型别名和原生统计，不能证明第三方网关内部物理模型实例。当前解释避免以这类不可观察信息作为实验前提。机器分类的进一步细分可在后续版本实现，并通过独立的重新评分记录保留版本关系。
