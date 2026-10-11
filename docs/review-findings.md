# 独立审阅与修复复核记录

初审日期：2026-10-12。审阅对象：首次完整实现快照 `work/momah-poc-2`；规范依据为 README、`docs/solution.md`、`docs/integration.md` 和用户要求。采用 code-review 的 Standards / Spec 两个检查轴；本次为初始实现全量审阅，无已有提交差异可比较。审阅 Agent 未修改实现，未调用任何模型或付费 API，未读取账户资料或临时 Key。

## Standards

仓库没有独立的 CODING_STANDARDS / CONTRIBUTING 文件。未发现需要单独报告的硬性规范违规；没有把代码简短、命名风格或未提供生产环境作为缺陷。Standards 轴发现数：0。

## Spec

初审：P0 0 项、P1 2 项、P2 4 项，共 6 项实际缺陷。以下问题已使用本地模拟或现有依赖复现，均无需真实模型调用。初审时所有问题状态为 **OPEN**，修复及独立复核结果请追加在文末，保留初始证据。

### R01 · P1 · 本机启动命令缺少 python-dotenv 依赖

- 位置：`pyproject.toml:10`，关联 `README.md:22` 的 `uvicorn --env-file .env` 命令。
- 要求：README 的本机运行步骤应在安装项目依赖后可运行。
- 实际行为：项目只安装 `uvicorn` 本体，没有声明 `python-dotenv`。现有测试 venv 中 `importlib.util.find_spec('dotenv')` 为 None；执行 `uvicorn.Config(..., env_file=...)` 直接报 `ModuleNotFoundError: No module named 'dotenv'`。Gateway 镜像构建的依赖清单也没有该包。21 项 pytest 不加载 `.env`，因此没有发现问题。
- 影响：严格按 README 安装后无法启动本机网站验证入口。
- 修复建议：明确增加固定版本的 `python-dotenv`，或移除 `--env-file` 并提供实际可用的环境注入方式。增加仅加载临时 `.env` 的启动配置回归，不需要调用模型。
- 初审状态：OPEN。

### R02 · P1 · 请求超时或进程中止会丢失预算预留

- 位置：`scripts/evaluate_tts_content.py:26`、`:44`；相同问题见 `scripts/evaluate_openrouter.py:65`、`:91`，`scripts/smoke_real_pipeline.py:31`。
- 要求：用户已授权累计最多 5 美元，失败或费用未知的请求也需要保留预算。
- 实际行为：`Budget.reserve()` 只改内存；费用台账在响应、解码和 settle 之后才写盘。续测脚本的 post/解码失败直接退出；初次脚本即使捕获普通异常，进程在请求期间被中断也没有 durable reservation。真实服务可能已经接收并计费，下一次运行却读取旧台账。
- 本地复现：创建 `committed=4.9` 的临时台账，模拟 TTS 请求发起后的 `httpx.ReadTimeout`。0.1 美元已在内存预留，但退出后 `cost.json` 仍记录 **4.9**。重复执行可反复忽略这些费用未知的请求。此次复现只用本地 OfflineClient，没有网络请求或费用。
- 影响：当前累计预算检查在失败/中止路径不能维持授权上限。现有 $1.503475 的记录并不意味着已发生超预算；问题在后续复现过程的预算保护。
- 修复建议：付费请求发出前原子持久化带唯一 call_id 的预留记录；异常/取消保持未知占用，成功再结算同一记录；共享台账应防止多个续测进程同时更新，避免重复结算与截断写入。为超时、取消、重启读取、超上限拒绝及台账损坏增加无网络测试。
- 初审状态：OPEN。

### R03 · P2 · 旧业务结果仍触发 TTS 推理

- 位置：`src/speech_gateway/runtime.py:86`–`:88`。
- 要求：取消后的旧 ASR / 业务 / TTS 任务应校验 epoch，迟到工作不得继续进入下一模型阶段。
- 实际行为：业务 provider 若吞掉 CancelledError 后返回旧结果，`guarded(reply, epoch)` 会正确返回 False，但返回值被忽略，代码继续调用 TTS。音频发送前的 epoch 检查会丢弃输出，因此未发现旧声音复活；错误是无效推理继续占用 semaphore 与模型资源。
- 本地复现：Fake ASR 立即返回；Fake business 在取消后仍返回 `{'reply':'stale response','handoff':False}`；在 business 等待时调用 interrupt。最终事件只有 stop/transcript/stop，但 Fake TTS 调用列表为 **['stale response']**。
- 修复建议：`guarded(reply)` 失败立即 return；在进入 TTS 及进入后续句子前检查 closed / transferred / epoch。增加 business 和 TTS 迟到回归，并断言旧任务不再调用后续 provider、释放 semaphore。
- 初审状态：OPEN。

### R04 · P2 · 旧连接的 close 回调会关闭重连的新会话

- 位置：`src/speech_gateway/web/index.html:12`、`:42`。
- 要求：网站结束会话后可以重新连接，旧回调不得操作新会话。
- 实际行为：finish 和所有 WebSocket 回调使用全局 `ws/ctx/stream`。用户点击结束时，finish 调用旧 ws.close() 并立即启用“开始”；如果新连接已经创建，随后到达的旧 ws.onclose 又调用 finish，关闭全局变量中的新连接及其麦克风。
- 本地复现：用 Node vm 加载原网页脚本和最小 DOM；保存旧 `onclose=finish`，先执行 finish，再将全局 ws 设为新 READY socket，最后调用旧 onclose。结果 **newSocketClosed=true, ready=false**。
- 修复建议：把每次连接资源和回调绑定到独立的 session 对象或 generation；关闭旧连接只清理该连接资源，旧 generation 回调不能改变新页面状态。补充“结束→立即开始→旧 close 到达”和重复 onerror/onclose 的客户端回归。
- 初审状态：OPEN。

### R05 · P2 · 逐位 ID 在分句边界失去原子保护

- 位置：`src/speech_gateway/text.py:27`、`:38`–`:44`；调用见 `runtime.py:87`。
- 要求：方案第 5 节承诺“先保护字段再分句”“不在标识符内切分”。
- 实际行为：prepare_speech 将 typed ID 替换为多个普通单词；chunks 不知道这些词属于一个 ID，仍逐词执行 180 字符切分。
- 本地复现：`reply='يرجى '*33+'1047'`，slot 为 `{'kind':'id','value':'1047'}`。结果第一 chunk 末尾是 **واحد صفر أربعة**，第二 chunk 单独为 **سبعة**。原始数字 token 未切开，但其实际朗读表示已被拆开。
- 影响：关键编号被分成两次独立合成，中间可能发生额外等待、音色变化或打断，与已声明的字段保护契约不符。
- 修复建议：保留 typed slot 的 span/原子片段信息到 chunk 阶段，或采用单一 prepare-and-chunk 接口，整体把逐位朗读片段放入下一 chunk；片段超长时明确拒绝。覆盖临界长度、多个 ID、最长允许 ID 和句末标点。
- 初审状态：OPEN。

### R06 · P2 · 模型全失败时无法生成报告，部分统计文字硬编码

- 位置：`scripts/build_report.py:21`–`:22`、`:34`、`:39`、`:46`、`:48`。
- 要求：测试失败应保留证据，报告应与实际执行结果一致。
- 实际行为：某模型/条件没有成功 scores 时，对空列表调用 np.percentile 直接异常。临时数据中放一条 HTTP503 的 ASR 结果即可复现 **IndexError: index -1 is out of bounds for axis 0 with size 0**。另外，“共120次成功”、六条合成成功、固定耗时和回读结论都是文字常量；新一次执行部分失败时会与动态结果表矛盾。
- 影响：接口不可用恰好需要失败报告时脚本不能完成；不同结果重跑后也可能生成不准确的验收叙述。现有历史报告的 120 次成功已与原始结果核对一致，本问题针对报告生成逻辑。
- 修复建议：零成功组保留 attempted/failed，延迟与 WER 为 null/未取得；成功数、时长、样本统计、TTS 判断从当前结果计算。缺少可选结果文件时明确“未执行”，不能默认通过。以全失败、部分失败和缺失可选测试结果做纯本地报告回归。
- 初审状态：OPEN。

## 已验证证据与明确限制

初审运行 `../speech-venv/bin/python -m pytest -q`：**21 passed，1 个 audioop 废弃提示**。检查实际原始结果：ASR 120 条均 HTTP200；manifest 为 20 条、114.04 秒、Najdi3/Hijazi6/Khaliji6/MSA5，与报告一致。预算文件为 cap=5、committed=1.5034749087、reported actual=0.0034749087、unknown=19。已检查 CPU 镜像构建日志，确认 Gateway 镜像构建成功；本审阅没有再次运行 Docker 或 CUDA 镜像。

Qwen / VoxCPM 原生包装器的调用参数与固定源码提交的接口一致；这一静态核对不代表目标 GPU 模型加载成功。[VoxCPM 固定源码](https://github.com/OpenBMB/VoxCPM/blob/cce58a5b59303c9bd63d12f23afe6a49a4a80c59/src/voxcpm/core.py)、[Qwen 固定源码](https://github.com/QwenLM/Qwen3-ASR/blob/7c6daf77a2421100f5fb066495372c00129d39ff/qwen_asr/inference/qwen3_asr.py)。

以下已经在方案/报告中明确声明，**不是本轮实现缺陷，也没有被计为通过**：

- Genesys Tenant 实联、签名/HMAC入口、真实 Architect 转接和坐席接通尚未验收；协议模拟不能代替它们。
- CUDA 模型加载、目标 GPU 吞吐与 500 路语音会话容量尚未实测。
- 当前整句推理后分帧播放，不是原生模型首音频流式推理。
- 业务 Agent 是契约替身；真实任务准确率和转人工 recall 尚未测量。
- 母语 MOS、扬声器回声、弱网与真实网站麦克风端到端尚未验收。
- SADA 小样本和 PCMU 人工劣化，不能替代授权业务电话集；公共演示后端权重 revision 未公开。
- 日期/金额发音词典、跨 Pod 媒体恢复、Avatar Runtime 仍在预留范围。

初审结论：Standards 0 项；Spec 6 项，其中最高严重度为 P1。修复后应由独立审阅 Agent 复核以上编号，记录新增测试及状态变更，再发布最终交付。

## 修复与独立复核

待主 Agent 修改后追加；初审本身未关闭任何问题。

## 独立复核结论（2026-10-12）

独立审阅 Agent 对修复后的共享快照重新运行 `../speech-venv/bin/python -m pytest -q`：**32 passed，0 skipped，1 个 audioop 废弃提示**，耗时 3.76 秒。另直接重跑初审触发场景及 Node 客户端验证；没有调用任何真实模型、付费 API 或账户接口，没有读取 Key，没有修改实现。

| 编号 | 独立核验结果 | 最终状态 |
|---|---|---|
| R01 | 固定 python-dotenv 已声明并可用；uvicorn.Config 加载临时.env，环境值实际为 ok | CLOSED |
| R02 | 实际续测入口的 ReadTimeout/CancelledError 回归通过；另独立启动子进程预留0.1美元后 os._exit(7)，重启读取仍占用5.0美元，下一次0.01预留被拒绝；并发、损坏台账与重复结算测试均通过 | CLOSED |
| R03 | 原吞取消的业务替身复现结果变为 stale_tts_calls=[]，semaphore恢复1；迟到空TTS不会进入下一句的回归通过 | CLOSED |
| R04 | 直接运行 node tests/test_client.cjs，旧close/error/message/capture回调及重复清理后新socket、AudioContext和ready状态保持正常 | CLOSED |
| R05 | 原“يرجى ”重复33次加1047的触发样例，末chunk为完整“واحد صفر أربعة سبعة”；多个ID、30位可容纳ID、超长拒绝及标点回归通过 | CLOSED |
| R06 | 独立传入全HTTP503结果和缺失可选文件，报告正常生成：failed=1、WER=null、P95=null；部分失败和空结果回归通过，成功数/时长/TTS统计从结果计算 | CLOSED |

本轮未发现需要新增的 P0/P1/P2 缺陷。初审 6 项全部独立关闭，当前审阅范围内 OPEN=0。此前 OPEN 和“待独立复核”文字属于初审/修复历史，以本表最终状态为准。

本结论仅确认这次代码及报告缺陷已修复；它不把协议模拟、公共API或演示结果升级为生产验收。最终 Gateway 镜像重建由主 Agent 另行核验；目标 CUDA 加载/吞吐、Genesys Tenant/转接、母语 MOS、真实麦克风/回声/弱网、真实业务准确率和500路容量仍按方案列为未测。

