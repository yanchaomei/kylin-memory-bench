# openKylin 长期记忆 Benchmark 实现计划

日期：2026-10-03。工具名：Kylin Memory Bench，命令 `kmb`。

## 作品目标

评测不同智能体跨会话使用长期记忆的能力，统一收集对话、记忆文件、执行轨迹和任务产物。六维结果分别为 persistence、retrieval、update、discrimination、boundary、reuse。重点贡献是基于证据与程序化真值的可解释评分，以及不同智能体和操作系统下可重复运行的统一协议。

## 首轮实现

1. 独立 Python 工具放在 `benchmarks/kylin-memory-bench`，保留原作品源码和交付材料。
2. 版本化 JSON 数据集包含事实、保留策略、会话阶段、干扰项、更新和验证项；Agent 只接收当前消息，不接收评分真值。
3. 生成固定 seed 的六维样例；Opaque canary、路径/枚举、相似实体、临时/凭据/噪声边界与文件任务分别分层。
4. 每案例建立独立 Agent 状态目录和工作目录。会话切换、进程重启、记忆快照及文件检查由运行器记录。
5. 评分器优先使用结构化回复、精确 canary/路径/枚举、记忆快照和实际文件内容，返回状态、原因和证据引用。不可观察项单列 coverage/inconclusive。
6. 接入通用 JSON 标准输入/输出适配器、实际 OpenClaw 与 Hermes CLI；测试替身只用于评分器校准与可复现工程自检。
7. 输出 JSON/CSV/HTML、六维雷达 SVG/PNG、每例解释、重复稳定性与证据摘要。生成 `.deb`、安装和目标系统检测脚本。
8. 在真实 Agent 上跑首轮六维样例；在 openKylin 上重复、核对系统身份和输出，再按 3—5 分钟流程录制。

## 校准与控制

| 检查 | 必要证据 |
|---|---|
| 评分正确性 | 已知正确、遗漏、混淆、旧值、错误保留、错误复用、仅声称行动、文件缺失的反例 |
| 无真值泄漏 | 适配器 stdin/argv 中不含 assertions、expected 或完整 dataset |
| 会话边界 | 查询使用新 session_id；同案例保留 Agent 状态，新案例状态隔离 |
| 行动真实性 | 产物存在、相对路径有效、JSON 内容正确；回答“已完成”不能代替文件 |
| 边界真实性 | 对答拒用与已配置记忆文件中的持久化分别评分；会话日志不冒充长期记忆库 |
| 重复稳定性 | 同一冻结数据三轮，逐项比较结果与可评分覆盖；独立任务数与重复数分别列出 |
| 证据完整性 | 数据、配置、源码、进程结果和文件摘要进入 manifest，缺失/改动由 verify 检出 |
| 平台可复现 | doctor 记录实际 `/etc/os-release`、Python、架构、桌面及 Agent 版本；openKylin 单独验收 |

## CLI 与交付

`kmb generate`、`validate`、`run`、`score`、`compare`、`verify`、`doctor`。核心运行、评分和 SVG 绘图全部使用标准库，Debian 包只声明 Python 依赖。

交付包含方案说明、JSON Schema、样例数据/运行证据/评分、完整源码与测试、两个真实 Agent 配置模板、目标系统脚本、deb 包、测试报告、雷达图以及真实桌面录制流程。真实 Agent 与校准替身的报告分开标识。

## 当前资源

本机已安装 OpenClaw 2026.3.8 和 Hermes 0.8.0；SKV_3 的独立目录有 Python 3.11 与 dpkg-deb。已完成六维数据、两款 CLI 适配、证据采集、自动评分、报告、45 项回归和两平台三轮校准。既有虚拟机 system 入口可见并已进入登录界面，正式 openKylin 桌面入口与同一可用模型入口待就绪。新目标验证不沿用旧 V11 成绩。
