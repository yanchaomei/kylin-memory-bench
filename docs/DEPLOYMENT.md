# 安装、部署与复现

## 环境

评测器要求 Python 3.10+，无第三方运行依赖。Linux、macOS 可直接运行；正式目标验收需在 openKylin 完成。参评框架及模型服务各自安装和配置。Debian 包不捆绑模型，不修改全局框架设置。

## 源码运行与用户级安装

```bash
python3 --version
python3 kmb doctor
bash scripts/install.sh
~/.local/bin/kmb --version
```

`PYTHON` 指定安装检查时的解释器，`PREFIX` 指定安装目录，`BIN_DIR` 指定命令位置。默认安装进用户目录，不需要 root。运行时也可以使用 `python3.11 kmb ...` 明确解释器。

## 批量配置

统一 API 模式可直接使用 `configs/real-api.json`，只需提前在当前进程环境中配置该文件指定的凭据变量。配置示例：

```json
{
  "agents": [
    {"name":"OpenClaw-API","adapter":"openclaw","model":"gpt-6-sol","base_url":"https://api.adslab.icu/v1","api_mode":"responses","api_key_env":"CODEX_RELAY_API_KEY","reasoning_effort":"off","timeout":180},
    {"name":"Hermes-API","adapter":"hermes","model":"gpt-6-sol","base_url":"https://api.adslab.icu/v1","api_mode":"responses","api_key_env":"CODEX_RELAY_API_KEY","reasoning_effort":"off","timeout":180}
  ]
}
```

若使用其他模型入口，修改两个模型配置并先确认两款 CLI 均能独立回答一个简单问题。`timeout` 单位是秒，包含模型和工具执行。不要把密钥放进这份 JSON；参评框架通过已有私有 profile 或环境变量获得凭据。API 地址需为支持该请求模型的 HTTPS 服务；环境变量名可替换为评审环境采用的名称。

```bash
python3 kmb run --dataset data/sample.json --config configs/real-api.json --repeat 3 --out results/real-eval
python3 kmb compare results/real-eval/*/repeat-* --out results/real-eval-report
```

目录已存在时运行器拒绝覆盖，用新的输出目录重跑。三轮是三个新案例状态空间，而非对同一份已经填好的记忆重复提问。

## 增量任务与完整轮次研究

`data/episodes-test-48.json` 包含 24 个独立任务配对、48 条案例、352 个阶段。每端三轮时，可以从源码目录并发调度六个完整轮次；单轮内部仍串行执行，不把同一任务的各阶段分配给不同 worker。

```bash
python3 scripts/run_study.py --dataset data/episodes-test-48.json --config configs/real-api.json --repeat 3 --parallel 6 --out results/full48-study
python3 scripts/analyze_study.py results/full48-study/*/repeat-* --out results/full48-report
```

长任务放在独立 tmux 会话中。先确认 `study.json` 的 `finished_runs` 等于 `requested_runs`，`source_unchanged` 与 `scheduler_unchanged` 均为 true，再生成正式对比。控制器成功退出仍可能包含原生 CLI 或模型异常，`stage_errors`、可评分覆盖和实际成功率应一起查看。

相同命令只复用已经完整核验的轮次；半轮、已预留但未完成的轮次或配置变化都会拒绝恢复。需要再次评测时创建新的研究目录，保留原记录。`--parallel` 为 1—8，选择时应考虑外部服务配额；并发产生的阶段时延仅作本配置运行诊断。

分析输出包括六维雷达、逐例证据、资料提供/扣除收益及 `reliability.html/json/csv`。`pass^3` 表示三轮全部成功的案例比例，不是三次中成功一次。定义、冻结版本与凭据交付见 `LINUX_STUDY_20261009.md`。上述脚本随完整源码提供，Debian 基础命令仍用 `kmb run/compare`。

将 `--dataset` 替换为 `data/dialogue-24.json` 可评测自然语言交接。两份数据不混在同一个 `compare` 命令中。登录账号模式的备用配置仍在 `configs/openclaw.json` 与 `configs/hermes.json`，使用前先检查账号本身的模型权限。

## Debian 包

```bash
python3 scripts/build_deb.py --out dist
dpkg-deb --info dist/kylin-memory-bench_0.2.0_all.deb
sudo apt install ./dist/kylin-memory-bench_0.2.0_all.deb
kmb doctor --require-openkylin
```

程序安装在 `/usr/lib/kylin-memory-bench`，命令在 `/usr/bin/kmb`，配置、样例与文档在 `/usr/share/kylin-memory-bench`。包不执行网络下载或改动 Agent 用户数据。构建要求 `dpkg-deb`；架构为 `all`，Python 最低版本通过包依赖声明。

0.2.0 包已经在 Ubuntu 24.04.1 x86_64 独立解包，核验版本启动、12-case/52-stage 增量校准、证据及配对报告。对应包为 `dist/kylin-memory-bench_0.2.0_all.deb`，验证记录在 `results/deb-v020-linux-verification/receipt.json`。该解包验证不需要更改系统安装状态；openKylin 的实际安装与桌面验收单独记录。

## 目标系统验收

```bash
REAL_AGENT_CONFIG=/absolute/path/to/two-agents.json REPEATS=3 bash scripts/accept_openkylin.sh
```

脚本先验证真实系统身份，再运行回归测试、生成 24 条数据、执行六种校准对照三轮，并在提供真实配置时执行真实智能体三轮与对比。正式录屏只展示真实 Agent 报告，校准结果用于证明评分器可靠。

## 结果检查

```bash
kmb verify results/real-eval/OpenClaw/repeat-001
kmb score results/real-eval/OpenClaw/repeat-001
```

HTML 不依赖在线脚本和字体，可离线打开。需要分享时，复制完整 run 目录和对比报告；不要只保留雷达图片而丢掉评分和证据。

退出码 `0` 表示命令流程完成，`2` 表示配置、格式、完整性或平台检查问题。流程完成不等于所有记忆任务通过：实际通过率以 `score.json` 为准。
