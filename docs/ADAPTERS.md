# 智能体接入协议

## 原生适配器

OpenClaw：运行 `openclaw agent --local --json --agent main --session-id ... --message ...`。使用独立 `OPENCLAW_STATE_DIR` 和 `OPENCLAW_CONFIG_PATH`，文件工具限于本案例目录，不启用消息渠道。`MEMORY.md` 与 `memory/*.md` 是长期存储观察范围；原生会话 JSONL 是工具轨迹。对已知模型调用报错单列运行问题。

Hermes：运行 `hermes chat -Q -q ... --source tool --toolsets memory,file`。使用独立 `HERMES_HOME` 和 `TERMINAL_CWD`，不恢复旧会话。解析 CLI 的最终回复与 `session_id` 尾行；长期快照只观察 `memories/MEMORY.md`、`USER.md`，SQLite 会话表只用于行动轨迹。不复制个人长期记忆和历史会话。

原生配置的模型可以更换，比较两款框架时应换成同一个后端。模型鉴权配置沿用框架私有目录，评测配置不放密钥。

## 通用 JSON 标准输入/输出

`json-command` 是独立子进程，不使用 shell 拼接。标准输入接收一个 JSON 请求：

```json
{
  "schema":"kmb.request/v1",
  "case_id":"reuse-0000",
  "phase_id":"reuse",
  "kind":"action",
  "session_id":"独立会话UUID",
  "message":"当前任务消息，不含评分真值",
  "workspace":"本条案例的任务目录"
}
```

标准输出必须是一个 JSON 对象，至少包含字符串 `response`。可提供实际原生 `session_id`；同案例重复使用同一原生会话会被检测。诊断写 stderr，不要混入协议 stdout。

```json
{"response":"{\"answer\":\"/srv/projects/example\"}","session_id":"native-session-id"}
```

桥接程序必须真正调用被测框架，不把本工具的正确答案或 fixture 行为当成智能体。每次调用是新会话，长期状态保存在 `{profile}`。`{workspace}` 只放本次任务产物。参考 `configs/json-command.example.json`。

## 记忆观察入口

Markdown/JSON 文件可以通过 `memory_patterns` 声明。根目录在私有 profile 或 workspace 之间选择，不读取全局用户目录。

SQLite 记忆库使用明确的只读查询：

```json
{
  "memory_patterns": [],
  "memory_databases": [
    {"path":"memory.db","query":"SELECT subject, key, value FROM durable_memory"}
  ]
}
```

文件不超过 1 MiB；SQLite 每次最多 1,000 行、1 MiB 导出，查询执行超过约 2 秒会中断。符号链接、路径越界、解码失败、超过限制与查询错误都记为不完整观察。没有声明范围的存储写入断言不判为成功。

只声明该框架真实使用的长期存储位置。某文件没有创建可以表示无写入，但空范围或采集失败不能表示「没有保存」。私有目录的会话日志、模型认证文件、缓存不能直接并入长期库得分。

## 安全与证据责任

桥接程序可访问本机，需使用可信源码。首版实现是工作目录与框架状态隔离，不是内核级沙箱。平台可进一步用 namespace、容器或 cgroup 封装同一协议；这些机制未启用时不宣称有系统级强隔离。

数据集和真值不写入 Agent 工作区，也不传进 Agent 当前请求。分享记录保存完整过程但不包含认证文件；实际 provider 密钥会遮盖，合成的边界测试值保持可核对。先核对 `kmb verify`，再复算评分和对比。
