# Kylin Memory Bench：顶会评测方法与运行证据独立调研

核对日期：**2026-10-09，Asia/Shanghai**。代码版本查询截止于 `2026-10-09T15:59:59Z`，即上海当日结束。范围：8 组直接相关记忆评测（PersonaMem 的后续版本并入同组），另以 tau-bench、OSWorld、SWE-bench 作为运行证据参考。只采信作者论文、作者项目/仓库、官方会议与官方协议；搜索摘要和第三方整理仅用于找入口，不作结论依据。

本次是**方法调研，不是实验复现或实现验收**：未运行作者评测、未调用生成/裁判模型、未读取实际凭据、未连接实验服务器、未操作 Git；仅创建本文件。主代理负责增量 episode、配对对照及统计协议，本文只提供来源核验、方法边界和验收建议。

## 1. 最重要的结论

1. **“记住并答对”与“正确维护并使用记忆”必须分开。** LongMemEval 提供答案位置与 QA 双层评价；HaluMem 进一步评价抽取、更新、QA。KMB 应继续保留回复、存储、轨迹、产物四类证据，补充各阶段的可观察范围，而不是把最终错误自动归因为检索失败。[LongMemEval 正式论文，§3.3](https://proceedings.iclr.cc/paper_files/paper/2025/file/d813d324dbf0598bbdc9c8e79740ed01-Paper-Conference.pdf)、[HaluMem，§5](https://arxiv.org/html/2511.03506v3#S5)
2. **更新正确不等于删除成功，拒答不等于没有存储。** LongMemEval 更新评分允许旧信息与正确新值并存；MemoryAgentBench 的选择性遗忘通过新事实作答评价。两者均不能替代 KMB 的声明存储范围检查，更不能证明未观察副本、运行时缓存或物理介质已擦除。[LongMemEval 评分脚本](https://github.com/xiaowu0162/LongMemEval/blob/9e0b455f4ef0e2ab8f2e582289761153549043fc/src/evaluation/evaluate_qa.py)、[MemoryAgentBench，§3.1 与附录 B.4](https://arxiv.org/html/2507.05257v4)
3. **任务复用需要跨会话依赖，不只是最后生成一个文件。** MemoryArena 在前一子任务行动与反馈中形成约束，再让后一会话使用；LongMemEval-V2 则主要评价从历史轨迹取证并回答，不是在线行动成功率。KMB 可结合前者的依赖设计与后者的取证分解，不能混用两种得分。[MemoryArena，§3.2](https://arxiv.org/html/2602.16313v2#S3.SS2)、[LME-V2 作者协议](https://xiaowu0162.github.io/longmemeval-v2/#evaluation)
4. **可信自动评分的首选是可执行真值，不是默认增加 LLM 裁判。** PersonaMem 主评测不使用 LLM judge；tau-bench 比较数据库终态，OSWorld 读取环境产物，SWE-bench 执行测试。开放语义任务才需要独立的裁判协议与人工校准。[PersonaMem，§4.1](https://arxiv.org/html/2504.14225v2)、[tau-bench 终态评分](https://github.com/sierra-research/tau-bench/blob/59a200c6d575d595120f1cb70fea53cef0632f6b/tau_bench/envs/base.py)、[OSWorld 评分入口](https://github.com/xlang-ai/OSWorld/blob/b138d348256078fa634fc3b73567a7337c793e6b/desktop_env/desktop_env.py)、[SWE-bench 评分器](https://github.com/SWE-bench/SWE-bench/blob/02e7a74ffd0b707aab73d203fe87bdc7c76afc8e/swebench/harness/grading.py)
5. **MemoryArena 与 MemArena 是两个不同工作，现均有官方会议条目。** 前者为 ICML 2026 Poster，侧重相互依赖的多会话行动；后者为 NeurIPS 2026 Poster，作者标明 Evaluations & Datasets Track，侧重个人视角、权限与隐私/效用平衡。不能互换论文编号、作者、代码或“六维”定义。[ICML 官方条目](https://icml.cc/virtual/2026/poster/64842)、[NeurIPS 官方条目](https://neurips.cc/virtual/2026/poster/139685)、[MemArena 作者版本与 track 声明](https://arxiv.org/abs/2608.02613v2)

## 2. 录用状态与版本边界

| 工作 / 作者 | 截至核对日的状态 | 一手核验依据与注意事项 |
|---|---|---|
| LongMemEval / Di Wu 等 | **ICLR 2025 已录用，Poster** | [官方条目](https://iclr.cc/virtual/2025/poster/28290)、[正式论文](https://proceedings.iclr.cc/paper_files/paper/2025/file/d813d324dbf0598bbdc9c8e79740ed01-Paper-Conference.pdf)。2025-09 cleaned 数据不是原始 release，版本不可混报。 |
| LoCoMo / Adyasha Maharana 等 | **ACL 2024 主会长文** | [ACL Anthology 正式记录](https://aclanthology.org/2024.acl-long.747/)。原论文包含 QA、事件总结、多模态生成；不能把第三方仅 QA 的变体称作完整 LoCoMo。 |
| MemoryAgentBench / Yuanzhe Hu、Yu Wang、Julian McAuley | **ICLR 2026 已录用，Poster** | [官方条目](https://iclr.cc/virtual/2026/poster/10010781)、[作者仓库录用公告](https://github.com/HUST-AI-HYZ/MemoryAgentBench)。[OpenReview](https://openreview.net/forum?id=DT7JyQC3MR) 本次访问遇到验证页，改用会议页面源码交叉确认。 |
| MemoryArena / Zexue He 等 | **ICML 2026 已录用，Poster，已核验官方状态** | [官方条目](https://icml.cc/virtual/2026/poster/64842)、[官方目录](https://icml.cc/Downloads/2026)、[作者 v2](https://arxiv.org/abs/2602.16313v2)。会议标题省略 `MemoryArena:`；官方页关联 [OpenReview JHYmxqS9Jv](https://openreview.net/forum?id=JHYmxqS9Jv)。不是仅凭 arXiv Comments 推定录用。 |
| PersonaMem / Bowen Jiang 等 | **COLM 2025；作者及作者机构明确列为会议论文** | [作者仓库](https://github.com/bowen-upenn/PersonaMem)、[作者机构会议论文记录](https://www.microsoft.com/en-us/research/event/colm-2025/publications/)、[作者论文 v2](https://arxiv.org/abs/2504.14225v2)。[OpenReview](https://openreview.net/forum?id=6ox8XZGOqP) 本次受验证页限制；官方决定记录尚未直接读取。 |
| PersonaMem-v2 / Bowen Jiang 等 | **按预印本引用；未取得正式录用证据** | [作者论文](https://arxiv.org/abs/2512.06688v1)。**不能继承 PersonaMem 的 COLM 2025 身份**；匿名 ACL 投稿版本不等于录用。 |
| HaluMem / Ding Chen 等 | **按预印本引用；未取得正式录用证据** | [作者 arXiv v3](https://arxiv.org/abs/2511.03506v3)、[作者代码](https://github.com/MemTensor/HaluMem)。发现匿名 ACL 稿入口但未取得会议正式记录，不能写成 ACL 已录用。 |
| LongMemEval-V2 / Di Wu 等 | **预印本，作者明确 Work in Progress** | [arXiv v1](https://arxiv.org/abs/2605.12493v1)、[作者项目页](https://xiaowu0162.github.io/longmemeval-v2/)。不能继承 v1 的 ICLR 2025 身份。 |
| MemArena / Jiadong Zhang、Xiaosong Ma | **NeurIPS 2026 已录用，Poster；作者标明 E&D Track** | [官方条目](https://neurips.cc/virtual/2026/poster/139685)、[作者 v2，2026-10-02](https://arxiv.org/abs/2608.02613v2)、[正式作者仓库](https://github.com/dereksodo/MemArena-Bench)。官方摘要仍有旧版数字；方法采用 v2 与正式仓库，不沿用匿名仓库旧结果。 |
| tau-bench / Shunyu Yao 等 | **ICLR 2025 已录用，Poster** | [官方条目](https://iclr.cc/virtual/2025/poster/28170)。本次研究原始 tau-bench 协议，不将 tau²/tau³ 的改版或结果并入；[作者仓库已警告原任务版本过时](https://github.com/sierra-research/tau-bench)。 |
| OSWorld / Tianbao Xie 等 | **NeurIPS 2024 Datasets and Benchmarks Track** | [正式会议记录](https://proceedings.neurips.cc/paper_files/paper/2024/hash/5d413e48f84dc61244b6be550f1cd8f5-Abstract-Datasets_and_Benchmarks_Track.html)。原版、Verified、后续扩展应分别冻结。 |
| SWE-bench / Carlos E. Jimenez 等 | **ICLR 2024 正式论文** | [正式会议记录](https://proceedings.iclr.cc/paper_files/paper/2024/hash/edac78c3e300629acfe6cbe9ca88fb84-Abstract-Conference.html)。Verified 是后续数据/协议版本，不是原论文的 2,294 题全量成绩。 |

说明：web 阅读器对部分会议详情页返回 restricted URL，但**直接读取官方 HTML 成功**，已核对标题、会议年、Poster 标识及 OpenReview 链接。没有登录或读取浏览器账号。检索不到正式条目只能说明“本次未核实”，不能证明论文未录用。

## 3. 八组核心记忆评测：论文与脚本交叉阅读

### 3.1 LongMemEval：答案正确率与证据召回分离

- **机制与真值**：500 题覆盖信息抽取、多会话推理、时间推理、知识更新、不可回答。题目/证据陈述经人工处理；时间戳历史包含 `answer_session_ids` 与轮次 `has_answer`，允许分别测证据检索和最终 QA。[正式论文，§3](https://proceedings.iclr.cc/paper_files/paper/2025/file/d813d324dbf0598bbdc9c8e79740ed01-Paper-Conference.pdf)、[数据格式](https://github.com/xiaowu0162/LongMemEval/blob/9e0b455f4ef0e2ab8f2e582289761153549043fc/README.md)
- **实际评分**：`get_anscheck_prompt` 按题型给裁判不同规则；时间差允许 off-by-one，更新允许回答含旧信息但正确给出新值，偏好不要求满足 rubric 所有点。脚本固定 `gpt-4o-2024-08-06`、温度 0，使用 yes/no 结果；论文报告与人工高一致度，不能外推为中文 OS 场景的校准结果。[QA 脚本](https://github.com/xiaowu0162/LongMemEval/blob/9e0b455f4ef0e2ab8f2e582289761153549043fc/src/evaluation/evaluate_qa.py)
- **检索与控制**：`evaluate_retrieval` 同时返回 `recall_any`、`recall_all`、NDCG；多跳题只找到一段证据不能视为证据齐全。原生检索评价排除没有证据位置的拒答题；oracle 只提供证据会话，是 reader 诊断条件，不是部署成绩。控制数据 release、检索粒度、top-k、reader 与输入格式。[检索实现](https://github.com/xiaowu0162/LongMemEval/blob/9e0b455f4ef0e2ab8f2e582289761153549043fc/src/retrieval/eval_utils.py)、[官方运行说明](https://github.com/xiaowu0162/LongMemEval/blob/9e0b455f4ef0e2ab8f2e582289761153549043fc/README.md)
- **对 KMB**：适用于长期保持、调用、更新、相近区分；若框架暴露召回记录，可增加“证据齐全但答错”诊断。不可照搬宽松更新规则到安全参数，也不可把 QA 分数叫 Recall@8。**可执行字段仍应采用本项目严格类型/值断言。**

### 3.2 LoCoMo：事件时间线与人工检查，谨慎对待词面指标

- **机制与真值**：先构造 persona 和时间事件图，再生成长期对话，人工核验/修订一致性。QA 标注答案和对话证据；同时设计事件总结及多模态生成，不只是终局 QA。[ACL 正式论文，§3–4](https://aclanthology.org/2024.acl-long.747.pdf)
- **实际评分**：`eval_question_answering` 对多跳答案按子答案计算 F1，其他主要 QA 类别用经英文归一化/词干处理的 token F1；对抗题检查指定拒答短语。代码中的 `exact_match_score` 是归一化词集合比较，并非 JSON 精确相等。[实际评分实现](https://github.com/snap-research/locomo/blob/3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376/task_eval/evaluation.py)
- **控制与风险**：同一人物/事件时间线不能拆散后当独立样本；固定问题类别、证据粒度、历史截断与检索条件。脚本在没有返回 context/evidence 对照时给 `all_recall` 添加 1，因此该字段不能脱离运行条件宣称完美召回。中文字段、文件路径和安全边界不适合直接采用英文 F1。[评分与召回分支](https://github.com/snap-research/locomo/blob/3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376/task_eval/evaluation.py)、[运行入口](https://github.com/snap-research/locomo/blob/3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376/task_eval/evaluate_qa.py)
- **对 KMB**：借鉴“先有一致的事件账本，后有自然语言表面表达”，用于多项目交接和相近实体；不把词面重合当成产物正确或边界成功。

### 3.3 MemoryAgentBench：增量注入与多查询，SF 不等于隐私删除

- **机制**：把长上下文拆成多轮输入，覆盖 Accurate Retrieval、Test-Time Learning、Long-Range Understanding、Selective Forgetting。FactConsolidation 将矛盾的新事实置于旧事实之后，测单跳/多跳的新事实使用；TTL 含从先前标注示例学习分类/推荐，不能直接等同于 OS 操作经验迁移。[作者论文，§3 与附录 B](https://arxiv.org/html/2507.05257v4)
- **真值与评分**：不同子集使用不同口径，实体 QA/FactConsolidation 有 Substring Exact Match，LongMemEval 与总结另有模型评分。`calculate_metrics` 同时计算 EM、F1、SubEM；`default_post_process` 可在完整输出与解析输出中取较高分。不能用“包含正确新值”证明“没有同时使用旧值”。[规则评分](https://github.com/HUST-AI-HYZ/MemoryAgentBench/blob/538026089d1a8a8eff05121d0db89b388f360eba/utils/eval_other_utils.py)、[LongMemEval 裁判脚本](https://github.com/HUST-AI-HYZ/MemoryAgentBench/blob/538026089d1a8a8eff05121d0db89b388f360eba/llm_based_eval/longmem_qa_evaluate.py)
- **重要控制**：`ConversationCreator` 支持 agent-specific chunk size，一次注入同一历史后回答多题，降低重复构建成本。块大小、注入顺序、query 是否反写记忆、每历史题数、上下文预算都需披露。`S*` 重新组合 LongMemEval 历史，不能与原版 S 得分直接比较。[分块与 QA 构造](https://github.com/HUST-AI-HYZ/MemoryAgentBench/blob/538026089d1a8a8eff05121d0db89b388f360eba/conversation_creator.py)、[数据与版本说明](https://github.com/HUST-AI-HYZ/MemoryAgentBench/blob/538026089d1a8a8eff05121d0db89b388f360eba/README.md)
- **命名差异**：正式论文使用 SF；当前 README 使用 Conflict Resolution。应按具体任务解释，不宣称两者都测试了可验证删除。
- **对 KMB**：支持主代理的增量 episode 方向。建议把“构建一次、多题查询”与“回答后继续学习”作为不同协议；同一 episode 的题目及重复运行不是独立样本。

### 3.4 MemoryArena：行动反馈形成记忆，依赖深度比终局答对更重要

- **机制与真值**：四类环境为组合购物、渐进搜索、群体旅行规划、数学/物理推理链。人工构造/核验子任务因果顺序与约束；每 episode 从空记忆开始，会话内行动获得观测，结束后更新记忆供后续子任务使用。[作者 v2，§3 与附录 A](https://arxiv.org/html/2602.16313v2)
- **评分**：论文区分任务 Success Rate、子任务 Progress Score、约束 soft Progress Score，并画随依赖深度变化的曲线。实际实现不是统一 LLM 分数：旅行脚本对每日槽位进行字符串近似核对，购物奖励结合目标 ASIN、属性、价格，属性可用模型裁判或字符串规则，推理脚本从 `is_correct` 日志聚合。[旅行评分](https://github.com/ZexueHe/MemoryArena/blob/6cd9de14b71915e39ac742a20dc33785e14b6aab/env/env_systems/travel_planner_env/eval.py)、[购物奖励](https://github.com/ZexueHe/MemoryArena/blob/6cd9de14b71915e39ac742a20dc33785e14b6aab/env/env_systems/web_shopping_env/compute_reward.py)、[推理聚合](https://github.com/ZexueHe/MemoryArena/blob/6cd9de14b71915e39ac742a20dc33785e14b6aab/env/env_systems/formal_reasoning_env/eval.py)
- **控制与代码边界**：固定任务 agent，再换记忆后端；分别统计存储、检索、行动预算及延迟。作者仓库标记 preview；旅行脚本按真值与已提交 ID 的交集聚合，推理脚本的终局状态取最后一题并有缺字段默认值。因此“完整 episode 全通过”“末题成功”“已提交部分的成功率”要分开，不能照抄聚合函数就假定分母完整。[仓库说明](https://github.com/ZexueHe/MemoryArena/blob/6cd9de14b71915e39ac742a20dc33785e14b6aab/README.md)、[旅行与推理源码](https://github.com/ZexueHe/MemoryArena/tree/6cd9de14b71915e39ac742a20dc33785e14b6aab/env/env_systems)
- **对 KMB**：任务复用应加入前期实际执行发现的随机约束、撤销反馈或失败修正，后续任务不重述该值；分别测关键约束、当前产物、整链完成和深度衰减。不能把跨框架成绩差异直接解释为某一记忆算法的因果贡献。

### 3.5 PersonaMem / PersonaMem-v2：知道偏好与应用偏好分离

- **PersonaMem 机制**：动态用户画像、多主题多会话历史，在给定历史前缀处选当前用户最合适的回应。正确选项对齐当前状态，干扰项可包含过时或无关偏好；选择顺序随机。主评测是四选一；论文中的 generative setting 是长度归一化选项似然，不是自由生成后让模型裁判打分。[作者论文，§3–4](https://arxiv.org/html/2504.14225v2)
- **实际脚本**：`Evaluation.extract_answer` 从 `<final_answer>` 后提取唯一正确选项，也有全回复回退；统计按 persona 与问题类型汇总。数据包含 `end_index_in_shared_context` 和距离最近偏好证据的元数据，必须截取当时可见前缀，避免未来信息泄漏。[选项判定](https://github.com/bowen-upenn/PersonaMem/blob/d07e6ade22e85e0e5d562247323a9c3e07553226/inference.py)、[汇总脚本](https://github.com/bowen-upenn/PersonaMem/blob/d07e6ade22e85e0e5d562247323a9c3e07553226/summarize_results.py)、[数据字段](https://github.com/bowen-upenn/PersonaMem/blob/d07e6ade22e85e0e5d562247323a9c3e07553226/README.md)
- **近期补充**：PersonaMem-v2 加入隐含偏好、第三人称/假设内容、偏好变化、用户要求忘记及敏感信息，强调从会话证据推断而非人口属性刻板印象。本文只借其构造原则，未把 v1 脚本称作 v2 完整复现，也未证实 v2 的正式 venue。[v2 作者论文，§2](https://arxiv.org/html/2512.06688v1)
- **对 KMB**：在现有六维下增加分层，而非另建无真值的“人格总分”：显式/隐式偏好、自述/第三方/假设、偏好提取/新任务应用、当前值/历史值。用相同候选操作或结构化产物比较应用效果，避免措辞风格掩盖错误操作。

### 3.6 HaluMem：最直接的逐阶段错误记忆诊断参考

- **机制与真值**：会话按时序注入；金标分别包含应抽取记忆、新旧更新对、QA 及来源记忆点。加入 assistant 提出但用户未确认的 interference，评价错误记忆是否进入系统。[作者 v3，§4–5](https://arxiv.org/html/2511.03506v3)
- **评分脚本**：抽取完整性与准确性、更新 Correct/Hallucination/Omission、QA 同类标签分开；裁判拿到参考答案与证据。`eval_tools.py` 明确既有缺失又有矛盾时优先 Hallucination，未知真值下给具体事实算幻觉；聚合保留全量与有效裁判结果的不同分母。[rubric 与输入](https://github.com/MemTensor/HaluMem/blob/718f16ff0c83413b1c86fa83fc13cc1a639871f9/eval/eval_tools.py)、[逐会话评价与聚合](https://github.com/MemTensor/HaluMem/blob/718f16ff0c83413b1c86fa83fc13cc1a639871f9/eval/evaluation.py)
- **重要边界**：操作级诊断需要 Add Dialogue、Get Dialogue Memory、Retrieve Memory 三类接口。作者明确 Zep 无法完整导出每会话抽取记忆，相关抽取指标不可准确计算；异步摄取完成时间也不能假定等于请求返回时间。不同后端读取 API/预算及回答提示并非天然完全相同。[接口与特例说明](https://github.com/MemTensor/HaluMem/blob/718f16ff0c83413b1c86fa83fc13cc1a639871f9/eval/README.md)、[回答提示](https://github.com/MemTensor/HaluMem/blob/718f16ff0c83413b1c86fa83fc13cc1a639871f9/eval/prompts.py)
- **对 KMB**：把 `omission`、`stale_update`、`confusion` 补成“首次在哪个可观察阶段发生”的诊断。没有完整存储或检索接口时标 `unobservable/inconclusive`，不得靠最终答错反推抽取失败；未知应拒答与知道但不得披露也应分开。

### 3.7 LongMemEval-V2：固定 reader 的经验取证与延迟分解

- **机制与真值**：人工整理网页/企业环境的历史 agent 轨迹，评价静态状态、动态变化、工作流、环境陷阱、错误前提。memory 返回紧凑证据，再交给固定 reader 回答；**它主要测经验取证，不直接要求重新完成 GUI 任务**。[作者论文](https://arxiv.org/html/2605.12493v1)、[作者协议](https://xiaowu0162.github.io/longmemeval-v2/#evaluation)
- **实际脚本**：harness 验证 question/haystack ID 一致性，记录 memory context 原始与截断 token、query 与 post-query 时间、prompt、原始/解析答案和用量。`qa_eval_metrics.py` 提供短语集合、顺序匹配、选择题等规则；错误前提和 gotchas 有专用模型判分，错误前提仅答 UNKNOWN 不算成功纠错。[harness](https://github.com/xiaowu0162/LongMemEval-V2/blob/2cc8c540bdb87fe6761629b585e727e1c4704520/evaluation/harness.py)、[评分器](https://github.com/xiaowu0162/LongMemEval-V2/blob/2cc8c540bdb87fe6761629b585e727e1c4704520/evaluation/qa_eval_metrics.py)
- **控制与对 KMB**：若增加“从历史失败中总结步骤”的诊断，固定 reader、证据 token 上限、查询预算及历史集；公开截断与取证轨迹。保留任务复用实际产物为主结果，经验 QA 为辅助。作者准确率/延迟 frontier 的秒级预算不能替代项目 CPU-only 检索 P95 红线。[作者运行配置](https://github.com/xiaowu0162/LongMemEval-V2/blob/2cc8c540bdb87fe6761629b585e727e1c4704520/README.md)

### 3.8 MemArena：个人可见证据、权限与效用，不能与 MemoryArena 混名

- **机制与真值**：MASim 生成共享社会世界，将历史投影为每个人真正观察到的会话；问题真值关联可见证据。六维为 cloze、metadata、factual QA、cross-session reasoning、calibrated abstention、permission-aware access，**不是 KMB 六维的同义命名**。[作者 v2，§3–5](https://arxiv.org/html/2608.02613v2)、[正式仓库与维度映射](https://github.com/dereksodo/MemArena-Bench/blob/9fc3d2b33182e9c3e8ca27ae49adc3ccb1b42fb4/README.md)
- **实际评分**：权限使用五标签 `DISCLOSE_CORRECT / DISCLOSE_WRONG / DONT_KNOW / REFUSE / OTHER`，在 ALLOW 与 DENY 两类分别计算效用与隐私，再取调和均值 `F1_PU`。当前 canonical 统计区分有明确 protected fact 的样本与不带事实的行为探针；不能混用旧稿总体分母。其 DENY 泄漏定义是 `DISCLOSE_CORRECT`，不能自动扩称“没有任何敏感信息流出”或“明确按政策拒绝”；KMB 禁止标记检查仍应独立保留。[权限评分源码](https://github.com/dereksodo/MemArena-Bench/blob/9fc3d2b33182e9c3e8ca27ae49adc3ccb1b42fb4/eval/src/permission_metrics.py)
- **裁判校准与控制**：作者提供人工多数标签、按维度一致率、Cohen's kappa、五标签及泄漏二元对照的分析脚本；平票、跳过和未匹配样本需单列。固定 reader × backend × seed，并使用 evidence-only oracle 区分“取不到”与“取到仍泄漏”。有脚本不等于本次复验其校准结果。[人工校准分析](https://github.com/dereksodo/MemArena-Bench/blob/9fc3d2b33182e9c3e8ca27ae49adc3ccb1b42fb4/memarena/human_calibration/analyze_judge_human.py)
- **对 KMB**：边界维度应同时报告合法信息效用和禁止项泄漏，避免“全部忘记”或“全部拒答”看似安全。权限拒绝、未知拒答、禁止持久化是三种不同合同。其 GB10/SGLang 加速端侧实验不是本项目 CPU-only 资源证据，不移植性能数字。

## 4. 三组运行证据参考：可执行评分优于自述

| 工作 | 真值与自动判分 | 可迁移控制 | 不能外推的地方 |
|---|---|---|---|
| tau-bench | 在同一初始数据库上执行 gold actions 得到目标终态，比较实际终态 hash；必要时核对用户可见输出。保留 `task_id / trial / reward / traj / info`。[终态代码](https://github.com/sierra-research/tau-bench/blob/59a200c6d575d595120f1cb70fea53cef0632f6b/tau_bench/envs/base.py)、[运行与指标](https://github.com/sierra-research/tau-bench/blob/59a200c6d575d595120f1cb70fea53cef0632f6b/tau_bench/run.py) | 每次重复恢复初始状态；固定用户模拟器与 agent、工具、策略、动作上限。`pass^k` 衡量 k 次都成功，不是 `pass@k` 的至少一次成功。[作者论文](https://arxiv.org/html/2406.12045) | 用户模拟器本身是模型；温度 0 不保证系统确定性。数据库终态一致不自动证明过程遵守每条策略，也不是跨会话记忆收益证明。 |
| OSWorld | 每题声明环境 setup、result getter、expected getter、metric；从真实环境/文件提取结果，不依据“已完成”文本。多个判据有组合方式。[环境与评价代码](https://github.com/xlang-ai/OSWorld/blob/b138d348256078fa634fc3b73567a7337c793e6b/desktop_env/desktop_env.py)、[正式论文](https://proceedings.neurips.cc/paper_files/paper/2024/file/5d413e48f84dc61244b6be550f1cd8f5-Paper-Datasets_and_Benchmarks_Track.pdf) | 固定 OS 镜像、软件、屏幕、观测/动作空间、预算；保存 trajectory、recording、配置和 result。[运行入口](https://github.com/xlang-ai/OSWorld/blob/b138d348256078fa634fc3b73567a7337c793e6b/run.py) | 保存视频是辅助轨迹，不替代文件检查；GUI 成功不证明长期记忆因果收益。本项目在 openKylin 的实际验证不能用 Ubuntu 结果代替。 |
| SWE-bench | 根据 `FAIL_TO_PASS` 验证修复，根据 `PASS_TO_PASS` 验证未破坏原行为；通过实例环境执行日志判分，非补丁文本相似度。[正式论文](https://proceedings.iclr.cc/paper_files/paper/2024/hash/edac78c3e300629acfe6cbe9ca88fb84-Abstract-Conference.html)、[评分实现](https://github.com/SWE-bench/SWE-bench/blob/02e7a74ffd0b707aab73d203fe87bdc7c76afc8e/swebench/harness/grading.py) | gold patch 验证环境能成功；完整日志、真正执行的测试、退出码和逐测试状态相互核对；缺失预测、空补丁、环境错误单列。[官方 quickstart](https://www.swebench.com/SWE-bench/guides/quickstart/)、[报告实现](https://github.com/SWE-bench/SWE-bench/blob/02e7a74ffd0b707aab73d203fe87bdc7c76afc8e/swebench/harness/reporting.py) | 测试能被绕过或未启动；不能把没有失败日志当成通过。这里的前后测试合同，不等于“两个 agent 的配对随机实验”。 |

### 4.1 配对与统计：来源支持什么，本文建议什么

**论文/脚本实际支持的控制**：相同任务 ID 与初始环境、固定 reader 换后端、oracle 诊断、重复试验、gold/实际终态比较。**本文建议的配对差值、cluster bootstrap、McNemar 属于 KMB 的统计设计建议，不能声称上述每篇论文都采用了这些方法。** NeurIPS 官方 checklist 要求说明误差来源、区间计算方法、假设、实验环境与复现路径，但不规定所有 benchmark 都必须使用同一种检验。[NeurIPS 官方 checklist，第 4–8 项](https://neurips.cc/public/guides/PaperChecklist)

给主代理的协议核对清单，不涉及实现：

- 配对单位为同一冻结 episode，在各实验臂中固定输入、环境和资源预算；恢复同一前缀状态后只干预目标记忆因素。no-memory 必须排除聊天历史、产物、缓存中的旁路信息，不只把一个 memory 开关设为 false。[MemoryArena 闭环定义](https://arxiv.org/html/2602.16313v2#S3.SS2)
- 区分 **总体成功率**、可评分正确率、覆盖率；两臂缺证据不能靠删去困难案例制造差值。完整对的差值与全分配样本结果同时公开，附不完整对数及原因。[SWE-bench 完整集合报告](https://github.com/SWE-bench/SWE-bench/blob/02e7a74ffd0b707aab73d203fe87bdc7c76afc8e/swebench/harness/reporting.py)、[HaluMem 全量/有效分母](https://github.com/MemTensor/HaluMem/blob/718f16ff0c83413b1c86fa83fc13cc1a639871f9/eval/evaluation.py)
- 同一用户、历史或 episode 的多个 query/phase/repeat 相关，应在独立生成的 episode 或用户层重采样；保留各层结果。二元独立案例可用配对 McNemar；多次重复先明确如何形成案例结果，不能把所有阶段当独立样本套用单轮 Wilson 区间。此处为统计建议，不是上游标准强制项。
- `pass^k = mean_i[ C(c_i,k) / C(n_i,k) ]` 表示从 n_i 次重复中抽 k 次全部成功的估计；需 `n_i >= k`，完整、可比较的重复集合。全部都失败也有很高“状态一致率”，所以一致率不等于可靠成功率。[tau-bench `display_metrics`](https://github.com/sierra-research/tau-bench/blob/59a200c6d575d595120f1cb70fea53cef0632f6b/tau_bench/run.py)
- 单独报告冷启动/热缓存、摄取/更新、检索、reader、工具行动、阶段 wall-clock；耗时上限和超时率与 P95 一起展示，不能从成功样本 P95 消除超时影响。[LME-V2 时间与截断记录](https://github.com/xiaowu0162/LongMemEval-V2/blob/2cc8c540bdb87fe6761629b585e727e1c4704520/evaluation/harness.py)

## 5. 与本项目六维及逐阶段证据的关系

本节依据本次读到的本地设计文档，不认证历史真实运行数字，也不推定主代理正在实现的接口已完成。[DESIGN.md](</Users/yanchaomei/Desktop/Working/2026 memory OS/openkylin_挑战杯/benchmarks/kylin-memory-bench/docs/DESIGN.md>)、[CODE_GUIDE.md](</Users/yanchaomei/Desktop/Working/2026 memory OS/openkylin_挑战杯/benchmarks/kylin-memory-bench/docs/CODE_GUIDE.md>)、[RELATED_WORK.md](</Users/yanchaomei/Desktop/Working/2026 memory OS/openkylin_挑战杯/benchmarks/kylin-memory-bench/docs/RELATED_WORK.md>)

| 现有维度 | 最相关来源 | 保留的设计 | 方法层需要补强的点 |
|---|---|---|---|
| 长期保持 | [LongMemEval](https://github.com/xiaowu0162/LongMemEval)、[LoCoMo](https://aclanthology.org/2024.acl-long.747/) | 新进程/会话，干扰后重复查询 | 控制证据距离、干扰量、重启与真实时间等待；“重启保持”不直接宣称“已验证多月保持”。 |
| 记忆调用 | [LongMemEval 检索](https://github.com/xiaowu0162/LongMemEval/blob/9e0b455f4ef0e2ab8f2e582289761153549043fc/src/retrieval/eval_utils.py)、[LME-V2](https://github.com/xiaowu0162/LongMemEval-V2) | 随机项目目标与干扰项、真值留在评测器 | 能观察时区分 evidence-any/all、召回与 reader；不能观察时不捏造内部召回分数。 |
| 动态更新 | [MemoryAgentBench](https://arxiv.org/html/2507.05257v4)、[HaluMem](https://arxiv.org/html/2511.03506v3) | v1 → v2 → 新会话查询、`stale_update` | 区分当前有效值、历史可追溯值、撤销、条件例外；重复回写旧值、误更新其他项目应是不同失败类型。 |
| 相近区分 | [PersonaMem](https://arxiv.org/html/2504.14225v2)、[MemArena](https://arxiv.org/html/2608.02613v2) | 相近实体与同名副本、不凭常识猜随机值 | 加入角色/说话人/归属/时间限定及假设文本；实体事实不能从另一用户或全知记录回流。 |
| 边界识别 | [PersonaMem-v2](https://arxiv.org/html/2512.06688v1)、[HaluMem](https://arxiv.org/html/2511.03506v3)、[MemArena 权限](https://github.com/dereksodo/MemArena-Bench/blob/9fc3d2b33182e9c3e8ca27ae49adc3ccb1b42fb4/eval/src/permission_metrics.py) | 禁止项 + 合法正向对照、逐阶段存储检查 | 不存储、不可回答、不得披露三个标签分开；用效用/泄漏双结果区分“真守边界”和“全部没记住”。 |
| 任务复用 | [MemoryArena](https://arxiv.org/html/2602.16313v2)、[OSWorld](https://github.com/xlang-ai/OSWorld)、[SWE-bench](https://github.com/SWE-bench/SWE-bench) | 实际文件、创建/更新时点、前后状态 | 加依赖深度、行动反馈、修正经验及不可旁路约束；以产物与终态为主，QA/轨迹为诊断。 |

### 5.1 逐阶段证据不是逐阶段真值：两者要显式连接

现有 `write / distract / update / query / action` 与 `request / process / stdout / response / phase` 记录可继续使用。建议在协议层明确下列连接，不要求新增强制黑箱内部接口：

| 观察层 | 应对照的真值 | 可判定什么 | 证据不完整时 |
|---|---|---|---|
| 输入/来源 | `fact_id`、来源事件、说话人/实体、当时有效版本、允许用途 | 是否提供了足够且合法的信息 | 标明数据或前置条件失效，不把任务交给裁判猜真值 |
| 写入/更新后的声明存储 | 应保留集合、禁止集合、版本变化 | 抽取遗漏、错误吸收、未更新、越界持久化 | 声明范围内 `unobservable/inconclusive`；不得称全系统无残留 |
| 查询时实际取证 | 金标证据集合与允许可见范围 | 漏召回、召回错对象/旧版本、非法来源 | 无取证接口则仅评价回复，保留诊断未知 |
| 回答 | 当时金标答案或允许拒答类型 | 错误事实、遗漏、实体混淆、未知/权限拒答 | 严格解析失败与语义失败分开 |
| 行动与产物 | 初始状态、目标终态、合法状态转换、前期依赖 | 口头完成、旧产物复用、错误参数、实际未完成 | 工具轨迹/产物缺失不能算成功 |

上表为 KMB 的综合建议：来源于 [HaluMem 操作级合同](https://arxiv.org/html/2511.03506v3#S5)、[LongMemEval 答案位置](https://github.com/xiaowu0162/LongMemEval/blob/9e0b455f4ef0e2ab8f2e582289761153549043fc/README.md)、[OSWorld result/expected getters](https://github.com/xlang-ai/OSWorld/blob/b138d348256078fa634fc3b73567a7337c793e6b/desktop_env/desktop_env.py)。快照反映“该时点、该范围的状态”，manifest 提供完整性，不提供独立身份认证；用户自述来源也不能替代系统采集来源。

## 6. 最值得落地的五项

### P0-1：冻结来源、时点与政策真值账本

每个原子事实记录 `fact_id / subject / source_event_id / role / asserted_at / valid_from / valid_to / revision / policy`；未知、不可披露、不可持久化分别标注。自然语言可以变化，真值账本不随模型回答变化。加入自述、引用、假设、未确认 assistant 错误记忆与合法正向对照，防止“最后一句自动胜出”。[LoCoMo 事件图与人工验证](https://aclanthology.org/2024.acl-long.747.pdf)、[PersonaMem-v2 归属与隐私设计](https://arxiv.org/html/2512.06688v1)、[HaluMem interference](https://arxiv.org/html/2511.03506v3)

**验收建议**：同一冻结历史的各阶段真值能离线重算；所有当前答案有来源 ID；未来事件、其他用户信息和假设文本不能进入当前金标。现有 `facts/revision/policy` 是基础，不需推翻六维。

### P0-2：依赖型任务复用与记忆干预对照

支持主代理既定的 episode/配对工作：让早期实际行动及反馈产生后续必要信息，加入失败修正或新约束；至少区分正常记忆、受控禁用/丢失记忆、合法 oracle 证据诊断。预算与 reader 保持相同，干预后消除聊天/文件旁路。oracle 不能把完整答案或敏感事实泄漏给被测 agent。[MemoryArena 闭环](https://arxiv.org/html/2602.16313v2#S3.SS2)、[LongMemEval oracle](https://github.com/xiaowu0162/LongMemEval/blob/9e0b455f4ef0e2ab8f2e582289761153549043fc/README.md)

**验收建议**：同一 episode 的臂间区别可审计；后续成功依赖早期信息而非常识；分别报告整链、关键约束、子任务进展和依赖深度。本文不重复实现，也不假定所有外部框架已支持可控禁用。

### P0-3：错误归因矩阵与不可观察状态

将已有状态扩为诊断轴：正确、遗漏、错误吸收、过时、混淆、禁止存储、禁止披露、口头行动、执行失败、证据不可观察。以第一次有证据的失效阶段定位；不能观察的步骤保持未知，并保留合法信息效用。[HaluMem 三阶段与可观察 API 特例](https://github.com/MemTensor/HaluMem/blob/718f16ff0c83413b1c86fa83fc13cc1a639871f9/eval/README.md)、[MemArena 隐私/效用定义](https://github.com/dereksodo/MemArena-Bench/blob/9fc3d2b33182e9c3e8ca27ae49adc3ccb1b42fb4/eval/src/permission_metrics.py)

**验收建议**：已知行为替身和故意缺快照/轨迹的校准样本进入预期维度；无快照不判无泄漏；全忘/全拒答不能得到完整边界成功。安全主判仍用全部断言合取，软诊断分不得冲抵硬失败。

### P0-4：规则主评分 + 语义附加协议，裁判本身也须校准

路径、版本、交接码、JSON 产物、终态继续用确定性规则，离线从原始证据重算。只在将来确有自由文本任务时，另设可选语义轨道，公开裁判精确模型版本、prompt/rubric、输入金标、原始输出、解析及重试；本次不引入、不运行裁判。[PersonaMem 无 judge 主评测](https://arxiv.org/html/2504.14225v2)、[SWE-bench 真执行防护](https://github.com/SWE-bench/SWE-bench/blob/02e7a74ffd0b707aab73d203fe87bdc7c76afc8e/swebench/harness/grading.py)

**验收建议**：人工盲审分层样本，报告每类混淆矩阵、一致率/kappa、缺失与争议数，测试否定、旧新值并列、部分答案、裁判指令注入、所有选项并列与伪造 PASSED 文本。不得继承 LongMemEval 的英文人工一致度；模型 judge 失败单列，不重试到出现通过为止。[LongMemEval 人工 meta-evaluation](https://proceedings.iclr.cc/paper_files/paper/2025/file/d813d324dbf0598bbdc9c8e79740ed01-Paper-Conference.pdf)、[MemArena 校准分析](https://github.com/dereksodo/MemArena-Bench/blob/9fc3d2b33182e9c3e8ca27ae49adc3ccb1b42fb4/memarena/human_calibration/analyze_judge_human.py)

### P1-5：版本、预算、重复可靠性和分层时延一起发布

每次绑定 dataset revision/hash、agent/harness/scorer 版本、精确模型配置、硬件/OS、工具、token/动作上限、会话恢复/缓存策略。给出单次成功、覆盖、配对差值区间、重复可靠成功和每阶段费用/时延，避免以高一致失败或成功子集低延迟宣传提升。[tau-bench 重复指标](https://github.com/sierra-research/tau-bench/blob/59a200c6d575d595120f1cb70fea53cef0632f6b/tau_bench/run.py)、[LME-V2 用量与时延](https://github.com/xiaowu0162/LongMemEval-V2/blob/2cc8c540bdb87fe6761629b585e727e1c4704520/evaluation/harness.py)、[NeurIPS 可复现/统计要求](https://neurips.cc/public/guides/PaperChecklist)

**验收建议**：由主代理的统计协议给出真正独立样本与重复次数；CPU-only 检索 P95 与 CLI 整阶段 P95 使用不同名称和计时点。正式 openKylin 证据与其他 OS 结果分别归档。预算不一致时报告准确率/成本权衡，不作单因素优越性判断。

## 7. 来源审计清单

以下是实际打开并阅读方法/协议相关内容的独立资料，不把搜索结果、同页重复访问、仓库目录枚举或失败访问计入阅读数量。共 **37 项论文/官方协议/官方文件**；代码阅读采用公开原文，不执行作者代码。论文阅读聚焦方法、评测及相关附录，不宣称复核所有证明或复现结果。

| ID | 一手资料与实际阅读位置 | 用途 |
|---|---|---|
| S01 | [LongMemEval 正式论文](https://proceedings.iclr.cc/paper_files/paper/2025/file/d813d324dbf0598bbdc9c8e79740ed01-Paper-Conference.pdf)，§3.2–3.3、A.4 | 人工真值、答案位置、judge 校准 |
| S02 | [LongMemEval README](https://github.com/xiaowu0162/LongMemEval/blob/9e0b455f4ef0e2ab8f2e582289761153549043fc/README.md)，数据/cleaned/oracle/检索 | 版本与评测条件 |
| S03 | [LongMemEval evaluate_qa.py](https://github.com/xiaowu0162/LongMemEval/blob/9e0b455f4ef0e2ab8f2e582289761153549043fc/src/evaluation/evaluate_qa.py)，`get_anscheck_prompt` | 按题型评分容忍边界 |
| S04 | [LongMemEval eval_utils.py](https://github.com/xiaowu0162/LongMemEval/blob/9e0b455f4ef0e2ab8f2e582289761153549043fc/src/retrieval/eval_utils.py) | recall-any/all、NDCG |
| S05 | [LoCoMo 正式论文](https://aclanthology.org/2024.acl-long.747.pdf)，构造/评测 | 时间事件图与任务覆盖 |
| S06 | [LoCoMo evaluation.py](https://github.com/snap-research/locomo/blob/3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376/task_eval/evaluation.py)，`eval_question_answering` | 英文 F1、拒答、召回默认值 |
| S07 | [MemoryAgentBench 作者论文 v4](https://arxiv.org/html/2507.05257v4)，§3、附录 B | 增量、SF、子集区别 |
| S08 | [MemoryAgentBench conversation_creator.py](https://github.com/HUST-AI-HYZ/MemoryAgentBench/blob/538026089d1a8a8eff05121d0db89b388f360eba/conversation_creator.py) | 分块、agent-specific chunk、多查询 |
| S09 | [MemoryAgentBench eval_other_utils.py](https://github.com/HUST-AI-HYZ/MemoryAgentBench/blob/538026089d1a8a8eff05121d0db89b388f360eba/utils/eval_other_utils.py)，metric/post-process | EM/F1/SubEM 和解析取优 |
| S10 | [MemoryAgentBench longmem_qa_evaluate.py](https://github.com/HUST-AI-HYZ/MemoryAgentBench/blob/538026089d1a8a8eff05121d0db89b388f360eba/llm_based_eval/longmem_qa_evaluate.py) | LongMemEval 子集 judge |
| S11 | [MemoryArena 作者论文 v2](https://arxiv.org/html/2602.16313v2)，§3–4、附录 A/B | 跨会话依赖、真值、progress |
| S12 | [MemoryArena travel eval.py](https://github.com/ZexueHe/MemoryArena/blob/6cd9de14b71915e39ac742a20dc33785e14b6aab/env/env_systems/travel_planner_env/eval.py) | 槽位评分与分母边界 |
| S13 | [MemoryArena compute_reward.py](https://github.com/ZexueHe/MemoryArena/blob/6cd9de14b71915e39ac742a20dc33785e14b6aab/env/env_systems/web_shopping_env/compute_reward.py)，奖励定义、attribute judge、CLI | 精确 ASIN/属性规则、可选 judge |
| S14 | [MemoryArena formal eval.py](https://github.com/ZexueHe/MemoryArena/blob/6cd9de14b71915e39ac742a20dc33785e14b6aab/env/env_systems/formal_reasoning_env/eval.py) | 终局与进展聚合不是同一口径 |
| S15 | [MemoryArena 官方 Poster](https://icml.cc/virtual/2026/poster/64842)，公开 HTML 标题/JSON-LD/类型/链接 | ICML 2026 官方身份 |
| S16 | [PersonaMem 作者论文 v2](https://arxiv.org/html/2504.14225v2)，§3–4 | 前缀时点、动态偏好、无 judge |
| S17 | [PersonaMem inference.py](https://github.com/bowen-upenn/PersonaMem/blob/d07e6ade22e85e0e5d562247323a9c3e07553226/inference.py)，`extract_answer` | 唯一选项与回退判定 |
| S18 | [PersonaMem summarize_results.py](https://github.com/bowen-upenn/PersonaMem/blob/d07e6ade22e85e0e5d562247323a9c3e07553226/summarize_results.py) | persona/类别聚合 |
| S19 | [PersonaMem-v2 作者论文](https://arxiv.org/html/2512.06688v1)，§2 | 隐式/假设/第三人内容/隐私 |
| S20 | [HaluMem 作者论文 v3](https://arxiv.org/html/2511.03506v3)，§4–6、附录 B/D | 操作真值、错误记忆、API 限制 |
| S21 | [HaluMem evaluation.py](https://github.com/MemTensor/HaluMem/blob/718f16ff0c83413b1c86fa83fc13cc1a639871f9/eval/evaluation.py)，`process_user/aggregate_eval_results` | 时序评分与全量/有效分母 |
| S22 | [HaluMem eval_tools.py](https://github.com/MemTensor/HaluMem/blob/718f16ff0c83413b1c86fa83fc13cc1a639871f9/eval/eval_tools.py)，评价 prompt/接口 | Correct/Hallucination/Omission 与冲突优先级 |
| S23 | [HaluMem eval/README.md](https://github.com/MemTensor/HaluMem/blob/718f16ff0c83413b1c86fa83fc13cc1a639871f9/eval/README.md)，特例 | Zep 不可观察、异步及预算 |
| S24 | [LME-V2 作者论文](https://arxiv.org/html/2605.12493v1)，方法/评测 | 环境经验取证任务 |
| S25 | [LME-V2 harness.py](https://github.com/xiaowu0162/LongMemEval-V2/blob/2cc8c540bdb87fe6761629b585e727e1c4704520/evaluation/harness.py)，ID 校验、prompt、per-question/聚合记录 | 固定 reader、token/截断/时延 |
| S26 | [LME-V2 qa_eval_metrics.py](https://github.com/xiaowu0162/LongMemEval-V2/blob/2cc8c540bdb87fe6761629b585e727e1c4704520/evaluation/qa_eval_metrics.py)，规范化/选择/专用 judge prompt | 混合判分合同 |
| S27 | [MemArena 作者论文 v2](https://arxiv.org/html/2608.02613v2)，设计/协议相关段落 | 自我视角、可见来源、权限 |
| S28 | [MemArena 正式 README](https://github.com/dereksodo/MemArena-Bench/blob/9fc3d2b33182e9c3e8ca27ae49adc3ccb1b42fb4/README.md) | 维度、reader/backend、版本说明 |
| S29 | [MemArena permission_metrics.py](https://github.com/dereksodo/MemArena-Bench/blob/9fc3d2b33182e9c3e8ca27ae49adc3ccb1b42fb4/eval/src/permission_metrics.py) | F1_PU、事实子集与旧版本区别 |
| S30 | [MemArena analyze_judge_human.py](https://github.com/dereksodo/MemArena-Bench/blob/9fc3d2b33182e9c3e8ca27ae49adc3ccb1b42fb4/memarena/human_calibration/analyze_judge_human.py) | 人工多数标签、一致率/kappa |
| S31 | [tau-bench 作者论文](https://arxiv.org/html/2406.12045)，评价/实验 | 终态真值、重复成功 |
| S32 | [tau-bench envs/base.py](https://github.com/sierra-research/tau-bench/blob/59a200c6d575d595120f1cb70fea53cef0632f6b/tau_bench/envs/base.py) 与 [run.py](https://github.com/sierra-research/tau-bench/blob/59a200c6d575d595120f1cb70fea53cef0632f6b/tau_bench/run.py) | gold actions、轨迹、pass^k；保守合计为 1 项 |
| S33 | [OSWorld 正式论文](https://proceedings.neurips.cc/paper_files/paper/2024/file/5d413e48f84dc61244b6be550f1cd8f5-Paper-Datasets_and_Benchmarks_Track.pdf) | 真实环境、execution-based evaluation |
| S34 | [OSWorld desktop_env.py](https://github.com/xlang-ai/OSWorld/blob/b138d348256078fa634fc3b73567a7337c793e6b/desktop_env/desktop_env.py)，reset/getter/evaluate 与 [run.py](https://github.com/xlang-ai/OSWorld/blob/b138d348256078fa634fc3b73567a7337c793e6b/run.py)，结果记录 | setup、产物、组合评价；合计 1 项 |
| S35 | [SWE-bench 正式论文记录](https://proceedings.iclr.cc/paper_files/paper/2024/hash/edac78c3e300629acfe6cbe9ca88fb84-Abstract-Conference.html) 与 [官方 quickstart](https://www.swebench.com/SWE-bench/guides/quickstart/) | 执行评分与 gold 环境自检；合计 1 项 |
| S36 | [SWE-bench grading.py](https://github.com/SWE-bench/SWE-bench/blob/02e7a74ffd0b707aab73d203fe87bdc7c76afc8e/swebench/harness/grading.py) 与 [reporting.py](https://github.com/SWE-bench/SWE-bench/blob/02e7a74ffd0b707aab73d203fe87bdc7c76afc8e/swebench/harness/reporting.py) | 真运行、退出码、失败分类与分母；合计 1 项 |
| S37 | [NeurIPS Paper Checklist](https://neurips.cc/public/guides/PaperChecklist)，第 4–8 项 | 复现、统计、环境与资源披露 |

### 7.1 固定的作者代码版本

通过公共 GitHub API 的提交元数据核对，不使用本地 Git，不把论文年份当源码版本。下表日期是 UTC committer date；正文代码链接已固定到完整 SHA。**源码日期、论文版本、数据 release 是三个独立对象。** 对动态作者网站不宣称已保存不可变网页快照。

| 作者仓库 | 本次阅读 SHA | 提交日期 (UTC) |
|---|---|---|
| xiaowu0162/LongMemEval | `9e0b455f4ef0e2ab8f2e582289761153549043fc` | 2026-05-11 |
| snap-research/locomo | `3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376` | 2024-08-13 |
| HUST-AI-HYZ/MemoryAgentBench | `538026089d1a8a8eff05121d0db89b388f360eba` | 2026-09-25 |
| ZexueHe/MemoryArena | `6cd9de14b71915e39ac742a20dc33785e14b6aab` | 2026-06-01 |
| bowen-upenn/PersonaMem | `d07e6ade22e85e0e5d562247323a9c3e07553226` | 2026-09-06 |
| MemTensor/HaluMem | `718f16ff0c83413b1c86fa83fc13cc1a639871f9` | 2026-09-03 |
| xiaowu0162/LongMemEval-V2 | `2cc8c540bdb87fe6761629b585e727e1c4704520` | 2026-08-09 |
| dereksodo/MemArena-Bench | `9fc3d2b33182e9c3e8ca27ae49adc3ccb1b42fb4` | 2026-10-01 |
| sierra-research/tau-bench | `59a200c6d575d595120f1cb70fea53cef0632f6b` | 2026-03-18 |
| xlang-ai/OSWorld | `b138d348256078fa634fc3b73567a7337c793e6b` | 2026-09-14 |
| SWE-bench/SWE-bench | `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e` | 2026-09-02 |

本地关系分析的文档快照 SHA-256：`DESIGN.md = 23d5ea240155bb2b1bace07aef6a86db5dd26fa42ad19e35bec836c69ee10b15`；`RELATED_WORK.md = 6856a8e7d5b67ee8499a656446c31b4baffc5d46f850020ba7bfe813d96c7143`；`CODE_GUIDE.md = 8fc95c41b13f8206eeaf0a353023bae3d440b013d9bc0ab8a4871da1f8b1b791`。若主代理修改设计，需按新版本重新核对映射，不能把这份调研视为新实现验收。

## 8. 仍需核实与不能据此宣称的事项

- **HaluMem、PersonaMem-v2 的正式 venue**：本次只有作者预印本/代码及匿名投稿入口，未取得录用证据；继续按预印本引用。**LongMemEval-V2** 作者仍标 Work in Progress，同样不列入已录用论文。[HaluMem](https://arxiv.org/abs/2511.03506v3)、[PersonaMem-v2](https://arxiv.org/abs/2512.06688v1)、[LME-V2](https://arxiv.org/abs/2605.12493v1)
- **PersonaMem 的官方决定页直接回读**：作者和作者机构已确认 COLM 2025，但本次 OpenReview 验证页阻止直接读取决定；这是证据渠道缺口，不是对其已录用身份的否定。[作者机构记录](https://www.microsoft.com/en-us/research/event/colm-2025/publications/)、[OpenReview 入口](https://openreview.net/forum?id=6ox8XZGOqP)
- **MemoryArena 的 ICML 2026 身份已闭合，不再标待核实**；后续复现仍要解决 preview 代码、数据版本、纸面模型名称/实际配置与各环境评分口径的绑定。**MemArena 的 NeurIPS 2026 身份也已核对官方条目**，但 track 的 E&D 标注来自作者版本。[ICML 官方条目](https://icml.cc/virtual/2026/poster/64842)、[NeurIPS 官方条目](https://neurips.cc/virtual/2026/poster/139685)
- 任何上游“高准确率”“人工一致度”“端侧搜索耗时”都不是本项目实测；合成多日历史不是多日墙钟等待，模型温度 0 不是确定性保证，正常答新值不是物理删除证明。[LongMemEval 评分合同](https://github.com/xiaowu0162/LongMemEval/blob/9e0b455f4ef0e2ab8f2e582289761153549043fc/src/evaluation/evaluate_qa.py)、[MemArena v2 资源与局限](https://arxiv.org/html/2608.02613v2)
- 与国际 benchmark 名称一致的维度，不构成同分数可比性或首创证据。KMB 当前最有价值的路线是：**围绕 OS Agent 的六维能力，用冻结真值、原生运行与声明范围内逐阶段证据建立可重算、可定位、可配对的评测合同**，再由正式实际运行支持效果与资源主张。
