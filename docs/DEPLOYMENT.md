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

将 `--dataset` 替换为 `data/dialogue-24.json` 可评测自然语言交接。两份数据不混在同一个 `compare` 命令中。登录账号模式的备用配置仍在 `configs/openclaw.json` 与 `configs/hermes.json`，使用前先检查账号本身的模型权限。

## Debian 包

```bash
python3 scripts/build_deb.py --out dist
dpkg-deb --info dist/kylin-memory-bench_0.2.0_all.deb
sudo apt install ./dist/kylin-memory-bench_0.2.0_all.deb
kmb doctor --require-openkylin
```

程序安装在 `/usr/lib/kylin-memory-bench`，命令在 `/usr/bin/kmb`，配置、样例与文档在 `/usr/share/kylin-memory-bench`。包不执行网络下载或改动 Agent 用户数据。构建要求 `dpkg-deb`；架构为 `all`，Python 最低版本通过包依赖声明。

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
