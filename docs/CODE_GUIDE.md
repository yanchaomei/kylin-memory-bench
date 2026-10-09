# 代码结构与模块职责

主程序不依赖原 MemoryOS-OK 的实现。评审方可以只下载这个目录并独立运行。

```text
kylin-memory-bench/
  kmb                         命令入口
  kylin_memory_bench/
    cli.py                    CLI 参数、批量工作流
    model.py                  数据契约、路径约束、JSON 解析与指纹
    dataset.py                六维场景的确定性生成
    episodes.py               注册增量任务、配对干预、完整再生成校验
    paired.py                 独立任务配对统计与固定 seed Bootstrap
    adapters.py               原生框架与通用协议适配
    runner.py                 子进程、会话、案例状态与证据采集
    evidence.py               文件/SQLite 快照和完整性清单
    scoring.py                验证项判定与维度统计
    reporting.py              重复对比、雷达图、HTML、CSV
    privacy.py                provider 凭据脱敏
    fixture.py                已知行为的校准替身
  configs/                    参评框架、批量配置与校准配置
  data/                       结构化样例、自然语言挑战、600 条扩展集、结构规范
  tests/                      标准库 unittest 回归
  scripts/                    安装、数据生成、目标验收、Debian/证据包构建、报告检查
  docs/                       方案、接入、部署、测试与演示说明
```

## 模块的输入与输出

| 模块 | 输入 | 输出 | 关键责任 |
|---|---|---|---|
| `model` | 数据字典、JSON 文本、相对路径 | 校验结果、规范序列化、SHA-256 | 明确数据版本，拒绝重复字段及越界路径 |
| `dataset` | seed、每维案例数 | `kmb.dataset/v1` | 生成事实、干扰、版本更新、边界和文件任务 |
| `episodes` | seed、事实世界、每维配对数、干扰数 | 冻结增量任务与两臂对照 | 两臂查询一致；控制源替换；完整重生成拒绝虚假配对 |
| `paired` | 同一冻结任务的独立运行评分 | 资料收益、覆盖、区间、逐配对记录 | 拒答与目标达成分开；重复先在配对内平均；不完整观察不制造收益 |
| `adapters` | 框架配置、当前请求、空白私有目录 | argv、子进程环境、回复、快照和轨迹 | API/OAuth 分支、显式推理配置、原生会话隔离；不继承用户历史，不覆盖 HOME |
| `runner` | 冻结数据、单款配置、输出目录 | `run.json` 与阶段证据 | 逐案例隔离、逐阶段重启、超时终止自身子进程 |
| `evidence` | 声明的文件/数据库、任务文件 | 有界快照、摘要、manifest | 区分长期库与会话日志；只读数据库 |
| `scoring` | 数据真值与运行证据 | 断言、案例、分维结果 | 不以完成声明代替文件，不以缺证据代替成功 |
| `reporting` | 同一数据上的多轮评分 | JSON、CSV、SVG、HTML | 分开真实 Agent 和替身，展示覆盖与一致性 |
| `privacy` | provider 密钥集合、诊断对象 | 脱敏诊断 | 不遮盖合成测试标记，保留评分信号 |
| `fixture` | 当前消息与独立状态文件 | 协议回复和实际任务产物 | 可预测正负对照，不访问 dataset 真值 |
| `cli` | 用户命令与配置路径 | 文件与退出码 | 完整性核对后才能重新评分和比较 |

## 一次真实运行的调用顺序

`cli.main` 读取并校验数据和配置，调用 `runner.run_benchmark`。运行器创建私有目录，然后为每条案例构造 `Adapter`。每阶段经 `adapter_request` 白名单生成请求，再调用 `execute` 启动子进程。适配器解析原生回复；运行器收集长期快照、工具轨迹和文件产物，写下阶段证据。最后 `score_run` 判定、`build_manifest` 冻结分享材料。

`compare` 不信任松散的评分 JSON：它先核对每个运行目录的完整性，再从该目录的冻结数据和运行证据重算分数，最后绘图。这样报告可回到原始阶段核查，而不只是手填几列数字。

## 新增框架或验证项

新增框架优先写独立 JSON-stdio bridge，不修改评分算法。声明该框架的长期存储位置；若采用 SQLite，用只读 SELECT 导出真正的记忆表，避免把会话消息表当作长期库。

新增任务时扩展数据案例和断言，用已知正例与反例校准，再加入测试。改变数据语义时应升级 schema 或冻结新数据指纹；不同指纹的数据不直接合并比较。

## 脚本与配置

| 文件 | 功能 |
|---|---|
| `configs/real-api.json` | 两款真实框架使用同一 HTTPS Responses 入口、模型别名和显式推理设置；凭据只写环境变量名称 |
| `scripts/generate_dialogue_challenge.py` | 把确定性的事实和阶段改为办公交接对话，保持核对规则和真值一致 |
| `scripts/install.sh` | 检查 Python 并安装到用户目录，不下载第三方运行库 |
| `scripts/accept_openkylin.sh` | 系统身份、回归、评分校准、真实 Agent 和报告的目标验收 |
| `scripts/build_deb.py` | 在 Linux 上构建架构无关的 Debian 包，包含代码、数据、配置、文档和协议 |
| `scripts/build_delivery.py` | 只收纳已验证的运行与报告，生成文件清单，完成 ZIP 内容回读校验 |
| `scripts/check_report.cjs` | 开发阶段用 Playwright 检查桌面/手机尺寸、筛选、展开和页面异常；不是评测器的运行依赖 |

OpenClaw 的原生回复保留 provider、model、session ID 和用量元数据。Hermes 从自己的 `state.db` 按当前会话导出消息和模型/用量；这组表明确作为执行轨迹，长期记忆仍然只观察其 `memories/MEMORY.md` 与 `USER.md`。
