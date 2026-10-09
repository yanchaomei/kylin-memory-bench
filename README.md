# Kylin Memory Bench

面向 openKylin 的智能体长期记忆自动化评测工具。

**一句话：不只看智能体是否答对，还核对它写了什么、更新了什么，以及是否真的用记忆完成了任务。**

本项目对应「面向 openKylin 操作系统的智能体长期记忆自动化评测 Benchmark 设计」。它是通用评测工具，不要求参评智能体使用 MemoryOS-OK。六个维度独立评分：长期保持、记忆调用、动态更新、相近区分、边界识别、任务复用。

## 0.2 增量任务与配对对照

新协议加入多次干扰、v1→v2→v3→迟到 v1、两次真实文件行动和资料可用性对照。同一任务两臂的查询/行动文字相同，分别提供或扣除目标资料，自动核对任务目标是否达成。正确拒答与目标达成分开计分；按独立任务配对重采样，保留覆盖率和置信区间。导入按注册生成器重新生成核对，拒绝改写实验臂、复制任务换 ID 或修改目标真值。

```bash
python3 kmb generate-episodes --seed 20261009 --split test --per-dimension 4 --interference-sessions 4 --out results/episodes.json
python3 kmb run --dataset results/episodes.json --config configs/real-api.json --out results/episode-agents
python3 kmb compare results/episode-agents/*/repeat-* --out results/episode-report
```

报告增加「配对资料收益」及 `paired_metrics.csv`。详细定义见 [增量任务协议](docs/EPISODIC_PROTOCOL.md)，参考工作及录用状态见 [顶会方法调研](docs/TOPCONF_METHODS_20261009.md)。这是资料可用性对照，不是声称关闭了框架全部记忆通道；当前留出按合成事实世界划分，不称为未见模板泛化。

本轮两款真实框架已各完成 88 阶段先导运行，观察到合法记录未调用、相近项目错误关联，以及独立的运行异常；完整配对为每端 5/6。全量 84 项回归、六种对照三轮及 808 阶段工程压力校准均已完成。结果、分母与原始证据见 [0.2 实测报告](docs/RESULTS_V020_20261009.md)。

## 快速运行

核心工具只依赖 Python 标准库，要求 Python 3.10 或更高版本。无需下载 embedding 模型、安装 ONNX Runtime 或连接模型服务，即可运行评分器校准。

```bash
cd benchmarks/kylin-memory-bench
python3 kmb doctor
python3 -m unittest discover -s tests -v
python3 kmb validate data/sample.json
python3 kmb run --dataset data/sample.json --config configs/calibration.json --out results/my-calibration --repeat 3
python3 kmb compare results/my-calibration/*/repeat-* --out results/my-calibration-report
```

报告生成在 `results/my-calibration-report/report.html`，浏览器直接打开即可。附有 `radar.svg`、`metrics.csv` 和 `comparison.json`。校准配置中的六种测试替身故意模拟正确保存、完全不保存、拒绝更新、实体混淆、错误保留以及只声称行动，用来检查评分器能否分清这些情况。它们与真实智能体报告分开。

## 评测真实智能体

原生适配器支持 OpenClaw、Hermes Agent，此外有通用 JSON 标准输入/输出协议。先确保参评智能体本身能完成一次模型调用，再选择配置。

```bash
python3 kmb run --dataset data/sample.json --config configs/real-api.json --repeat 3 --out results/real-eval
python3 kmb compare results/real-eval/*/repeat-* --out results/real-report
```

已验证的统一 API 配置是 `configs/real-api.json`，两款框架使用同一 `gpt-6-sol` 请求模型，接入方式见 [API 后端说明](docs/API_BACKEND.md)。`openclaw.json`、`hermes.json` 和 `*-anthropic.json` 是登录后端及备用模板，使用前必须验证对应账号和模型服务。配置中不填密钥。每条案例使用全新的框架状态目录，不继承个人记忆、聊天历史或消息渠道。每个阶段开新进程和新会话，同案例保留长期存储，不同案例完全分开。

已配置模型凭据环境变量时，可直接使用 HTTPS API 评测自然语言办公交接：

```bash
python3 kmb run --dataset data/dialogue-24.json --config configs/real-api.json --out results/dialogue-eval
python3 kmb compare results/dialogue-eval/*/repeat-* --out results/dialogue-report
```

导入多款智能体时，将配置放进 `{"agents": [...]}` 列表，用同一条 `run` 命令批量执行。第三方接入见 [适配器协议](docs/ADAPTERS.md)。

## 数据与结果

| 文件 | 用途 |
|---|---|
| `data/sample.json` | 24 条案例，六维各 4 条，覆盖四种不应保留的信息 |
| `data/core-600.json` | 600 条程序化生成案例，六维各 100 条 |
| `data/dialogue-24.json` | 24 条自然语言办公交接，含英文登记、中文查询 |
| `data/episodes-pilot-12.json` | 6 个配对、12 条案例、88 个阶段的先导集 |
| `data/episodes-development-48.json` | 24 个配对、48 条案例的开发事实世界 |
| `data/episodes-test-48.json` | 独立测试事实世界，48 条案例、352 个阶段 |
| `data/dataset.schema.json` | 可扩展的数据结构规范 |
| `results/*/dataset.json` | 本轮冻结数据及其真值 |
| `results/*/run.json` | 环境、配置、源码指纹与逐阶段运行记录 |
| `results/*/evidence/` | 当前消息、实际命令、原始输出、回复、记忆快照与工具轨迹 |
| `results/*/score.json` | 逐项结果、原因、证据引用与多维统计 |
| `results/*/manifest.json` | 分享材料的文件清单、大小和 SHA-256 |

数据使用合成项目名、合成路径和随机交接标记，不包含真实用户隐私。固定 seed 可重新生成完全一致的数据。600 条案例是可扩展数据集，不是已完成的 600 条真实 Agent 测试。

```bash
python3 kmb generate --seed 20261003 --per-dimension 100 --out data/core-600.json
python3 kmb verify results/openclaw/OpenClaw/repeat-001
python3 kmb score results/openclaw/OpenClaw/repeat-001
```

雷达图使用「成功案例 / 全部案例」；另外展示可评分正确率、证据覆盖率和重复一致率。模型鉴权失败、超时、缺少存储观察范围等都有单独状态，不会因为没有观察到错误就获得成功分。

### 已完成的真实运行

OpenClaw 与 Hermes 各完成结构化样例 3 轮，共 144 次案例执行、528 个阶段。OpenClaw 长期保持三轮平均 91.67%，Hermes 为 100%；两端调用、更新、区分、任务复用均为 100%。边界案例发现两端会误用相近合法项目值，完整判定为 0%，并附禁止值存储检查、未知查询与正向对照的逐项证据。完整结果与运行配置见 [测试报告](docs/TEST_REPORT.md)。

这是评测工具的真实区分结果，不是被测框架的宣传排行榜。不同数据集分别生成报告；自然语言挑战集的结果不会与结构化样例合并。工程回归在 macOS arm64 与 Linux x86_64 各通过 71 项测试。

HTTPS 自然语言挑战集也已完成真实单轮评测：两款框架各 24 条案例、88 个阶段、52 个断言全部通过；原生模型记录和工具轨迹完整。两份数据同时呈现明确交接与相近实体的不同表现。合计已归档 8 个真实运行、192 次案例执行、704 个阶段，按数据集与运行配置分别统计。

## openKylin 部署

无需联网安装评测工具：

```bash
bash scripts/install.sh
~/.local/bin/kmb doctor --require-openkylin
```

Debian 包在 Linux 下构建：

```bash
python3 scripts/build_deb.py --out dist
sudo apt install ./dist/kylin-memory-bench_0.2.0_all.deb
kmb doctor --require-openkylin
```

全链路目标系统验收：

```bash
REAL_AGENT_CONFIG=/absolute/path/to/two-agents.json bash scripts/accept_openkylin.sh
```

`doctor` 按实际 `/etc/os-release` 中的 `ID=openkylin` 判断平台，不把其他发行版的兼容标记当作 openKylin 实测。

## 文档

- [方案说明](docs/DESIGN.md)：目标、算法流程、对象和指标。
- [项目故事](docs/story.md)：问题、洞察、技术方案与演示主线。
- [相关工作](docs/RELATED_WORK.md)：与公开记忆评测的关系和设计取舍。
- [自然语言挑战集](docs/DIALOGUE_CHALLENGE.md)：办公交接、跨语言查询与冻结真值。
- [适配器协议](docs/ADAPTERS.md)：原生框架与第三方接入。
- [代码结构](docs/CODE_GUIDE.md)：每个模块的职责、输入和输出。
- [部署与复现](docs/DEPLOYMENT.md)：环境、安装、批量配置、结果验收。
- [测试报告](docs/TEST_REPORT.md)：本轮实测数据与待完成的目标验证。
- [录屏脚本](docs/DEMO.md)：3—5 分钟真实桌面演示流程。
- [交付清单](docs/DELIVERY.md)：逐项对应赛题要求。

代码协议为 Apache-2.0，见 `LICENSE`。程序化数据按 CC-BY-4.0 发布，见 `data/LICENSE.md`。参评框架遵循各自协议，不随本工具捆绑分发其模型、源码或账号凭据。
