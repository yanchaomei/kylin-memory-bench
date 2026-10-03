# 两款真实智能体的统一 API 接入

## 当前连接

配置文件：`configs/real-api.json`。两款智能体使用同一 `gpt-6-sol` 请求模型和同一 Responses API 网关。当前入口为 `https://api.adslab.icu/v1`，已通过默认 TLS 证书校验并完成一次真实生成，服务端返回 `status=completed`、`model=gpt-6-sol`。

认证只读取 `CODEX_RELAY_API_KEY` 环境变量。源码、配置模板、公开运行记录不存储密钥；不需要复制用户的 OpenAI 登录凭据或个人记忆。

```bash
python3 kmb run --dataset data/sample.json --config configs/real-api.json --repeat 3 --out results/real-api
python3 kmb compare results/real-api/*/repeat-* --out results/real-api-report
```

`base_url` 要完整保留协议、主机和 API 前缀。公网接入使用 HTTPS，不关闭证书校验。`api_key_env` 是环境变量名称，不是密钥内容。2026-10-03 的结构化数据三轮历史记录使用当时的 HTTP 入口，其配置和证据原样保留；本次 HTTPS 运行采用新的独立目录，不改写历史记录。

## 推理设置与运行记录

配置显式指定 `reasoning_effort=off`：OpenClaw 对应 `--thinking off`，Hermes 对应原生 `agent.reasoning_effort=none`。也支持共同使用 `low`、`medium`、`high`，比较时必须一起设置。未配置该字段的旧记录保留各框架当时的原生默认行为。

该设置控制客户端请求行为，不强制服务端的内部 token 预算。Hermes 原生会话表中的模型名、输入 token、输出 token 和 reasoning token 单独采集；OpenClaw 保留原生 `agentMeta`。实际用量与耗时以运行证据为准，不用推理设置标签推算。新记录不与旧推理配置合并成重复轮次。

## 原生接入方式

OpenClaw 使用 `openai-responses` provider，模型名为 `kmb-api/gpt-6-sol`。私有 provider 配置使用 `${CODEX_RELAY_API_KEY}` 引用，不把值写入配置文件。没有额外技能注入，文件工具限制在当前案例目录。

Hermes 使用私有 `config.yaml` 中的 `provider=custom`、`api_mode=codex_responses` 和完整 `base_url`；其子进程通过 `OPENAI_API_KEY` 获得同一凭据。当前安装版本的 CLI 不接受 `--provider custom`；显式传 `auto` 还会覆盖已配置的 custom 路由。因此 API 模式不传这项 CLI 参数，由私有配置指定 provider。

Hermes 工具轨迹通过只读 SQLite 查询按当前原生会话 ID 导出，并追加该会话的模型名及用量；不导出 `model_config`、认证文件、个人记忆或其他会话。上游网关的内部模型调度不属于本工具的观察范围。

## 会话与输出适配

本机 OpenClaw 版本会复用 `main` 会话索引，单独传新 `--session-id` 不足以保证新对话。因此每个阶段前仅清理本工具新建的私有会话目录，保留 `MEMORY.md` 与 `memory/*.md`，上一阶段的会话轨迹已收入分享证据。用户全局目录不改动。

Hermes 的静默输出可能保留一行流式界面标题。适配器只移除已确认的标题语法和会话尾行，并统一传输换行；不会从任意说明文本中抽取答案。原始 stdout 仍保留。证据校验按 UTF-8 原始字节解码核对回复，避免跨平台换行变换造成不一致。

这些适配点都已加入回归，防止当前对话上下文被当成长期记忆、界面装饰被当成模型答复，以及模型接口失败被计为有效生成。

## 实测口径

真实 API 运行与六种校准替身分别报告。每轮使用 24 条案例、88 个阶段、52 个断言，三轮均使用新的案例状态目录。指标从实际模型回复、长期记录和文件产物自动计算。

首轮已出现可以解释的边界失败：禁止标记没有写入长期文件，但模型把相近「已批准」项目的值回答给不应保留的项目。它属于未知项目的错误回答／错误关联，不表述为敏感标记泄漏。逐例原因和实际值必须与这个区别保持一致。
