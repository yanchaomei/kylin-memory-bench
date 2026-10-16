# 三项核心技术演示与复现指南

材料版本：R2，2026-10-16。工具版本仍为 0.2.0，核心源码和实验输入不变。本轮仅重组作品说明、章节字幕与中文讲解，沿用已归档的真实屏幕素材，不重新运行模型。

## 演示主线

让智能体在新会话里完成依赖历史资料的任务，再核对资料是否用对、边界是否遵守，以及能否在相同条件下持续成功。

| 成片时间 | 场景 ID | 画面与动作 | 应观察到什么 |
|---|---|---|---|
| 00:00-00:30 | 01_environment | 实际 UKUI 终端、系统身份及原生 CLI 版本 | openKylin 2.0 SP2、两款真实框架、目标平台 96 项测试记录 |
| 00:30-01:04 | 02_protocol | 查看冻结 JSON 与版本阶段 | 技术一：事实逐步输入，评分真值不进入当前请求；两臂只改变相关资料可用性 |
| 01:04-01:39 | 03_live | 实际运行记录驱动的进度、记忆与任务文件监视 | 两端分别执行阶段，保留原始编号和状态；等待加速已标注 |
| 01:39-02:11 | 04_action | 展开检查点与最终交接文件 | 初始码与反馈后的新码不同，实际文件内容和本次行动状态可核查 |
| 02:11-02:44 | 05_target_results | 目标平台雷达图、失败筛选与断言展开 | 技术二：四路证据区分错误关联、禁止项存储、合法项保留和运行异常 |
| 02:44-03:17 | 06_full_study | 单独归档的 Ubuntu 三轮报告 | 技术三：三轮全部成功比例与状态一致率不同，覆盖与异常同时展示 |
| 03:17-03:51 | 07_reproduce | 核验两份目标平台 run，查看导出格式与代码入口 | 原始证据可离线核验及重评分，不依赖人工填写总分 |

时间按最终 231 秒成片取整；精确切点见视频回执。录屏来自 2026-10-16 的 openKylin UKUI 会话；完整三轮研究运行于 2026-10-09 的 Ubuntu，2026-10-16 收回并核验。屏幕素材顺序未改变，主要压缩实际等待。旁白采用微软“晓晓”普通话神经女声 `zh-CN-XiaoxiaoNeural`，语速 `-8%`，完整保留、不截句、不作后期加速；不是 Agent 输出。视频内置可开关的中文字幕轨，另附 SRT 文件。

## 先离线复现，不需要模型账号

在源码根目录执行：

```bash
python3 kmb doctor
python3 kmb validate data/episodes-pilot-12.json
python3 kmb run --dataset data/sample.json --config configs/calibration.json --out results/my-calibration
python3 kmb compare results/my-calibration/*/repeat-* --out results/my-calibration-report
```

预期：六种已知行为分别呈现正确记忆、不持久化、旧值、实体混淆、错误持久化、口头行动的不同模式。它们是评分器校准，不是真实智能体排名。

从提交包重算真实结果，不调用模型。邮件包为缩小附件体积将完整三轮原始目录单独压缩，先按包内复现说明展开；完整离线包已展开原始目录：

```bash
python3 kmb verify results/openkylin-episodes-20261016/OpenClaw-API/repeat-001
python3 kmb verify results/openkylin-episodes-20261016/Hermes-API/repeat-001
python3 kmb compare results/openkylin-episodes-20261016/*/repeat-* --out results/my-target-report
python3 scripts/analyze_study.py results/full48-linux-20261009/*/repeat-* --out results/my-full48-report
```

预期：目标平台每端 11 通过、1 失败、0 不可评分；六维依次为 100/100/100/100/50/100%。Ubuntu 三轮全成功比例为 Hermes 43/48、OpenClaw 34/48，原始平台分开报告。

## 在 openKylin 重新运行真实框架

先按 `DEPLOYMENT.md`、`API_BACKEND.md` 安装固定版本的 OpenClaw 与 Hermes，配置共同模型入口及 `configs/real-api.json` 指定的凭据环境变量。不要将密钥写在命令参数、截图或提交材料中。

```bash
python3 kmb doctor --require-openkylin
python3 scripts/run_study.py --dataset data/episodes-pilot-12.json --config configs/real-api.json --out results/my-native-target --repeat 1 --parallel 2
python3 kmb compare results/my-native-target/*/repeat-* --out results/my-native-target-report
```

每款框架 12 案例、88 阶段，两端共 176 阶段。墙钟时间受模型服务、工具执行与证据采集影响；3 分 51 秒是剪辑成片时长，不是完整运行耗时。框架版本与模型配置改变时应建立新运行目录，不覆盖旧证据。

## 常见问题

- `doctor` 未识别 openKylin：先核对实际系统；其他 Linux 可运行核心流程，但另存平台结果。
- API 超时或协议错误：保留原文、阶段状态及不可评分标记；检查网络和原生 CLI，不把后续成功回填旧案例。
- 证据核验失败：查看清单差异和阶段关联，不手工改分数；如需重跑，使用新的输出目录。
- 只出现“已完成”但没有文件：这是任务复用失败，需要查看实际工具轨迹与产物，不应修改评分器放行。
- 视频听感：制作方完成时长、图面与解码检查；发布前请完整播放，确认术语发音、数字与章节同步。
