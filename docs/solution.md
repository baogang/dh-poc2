# ASR/TTS集成解决方案V1

## 1. 方案结论与边界

本方案以可私有部署的 Speech Gateway 统一网站语音与 Genesys IVR 接入，采用开源模型与可替换接口，优先评估 Qwen3-ASR 1.7B、Nemotron 3.5 ASR 和 VoxCPM2。Gateway 负责媒体与语音回合，业务 Agent 负责知识、业务规则和工具调用。Genesys 保留电话接入、排队、坐席与转接的控制权。当前 PoC 不启用 LiveKit，Avatar Runtime 为独立预留模块。

本次交付是可运行的集成 PoC及技术验证：网站入口、Genesys 协议适配、真实 VAD、ASR/TTS 接口、打断、限流、转人工请求、评估脚本与私有模型服务包装器均有代码。真实模型测试已执行；Genesys Tenant 实联、目标 CUDA 环境、母语听评和生产负载验收需要在实施环境完成。现有结果支持继续评估，不能签署生产准确率或容量达标。

总体图见 `diagrams/overview.html`。图中的组件按部署或职责聚合，下表列出完整逻辑模块，因此图中的方框数量不等于模块数量。

## 2. 模块清单与开源覆盖

当前需要 **13 个逻辑模块**，未来新增 **M14 Avatar Runtime**。逻辑模块不等于微服务；M03/M04/M05/M07/M09/M11 可共同部署在一个 Gateway 进程，ASR 和 TTS 独立部署，业务 Agent 使用既有平台。

| 模块 | 用途与本次实现 | 采用方案/已覆盖范围 | 可替代方案及取舍 |
|---|---|---|---|
| M01 网站接入 | 麦克风、AEC、PCM16 16kHz、播放队列、停止播放、独立访客会话 | 浏览器 Web Audio/AudioWorklet；`web/` | Pipecat SmallWebRTC 更适合弱网、拥塞控制和抖动缓冲；需 ICE/TURN。PoC 的 WebSocket 简单，但公网弱网需专项验收 |
| M02 Genesys 接入 | v2 open/ping/close/DTMF、序号、PCMU 8kHz external 单声道；协议模拟测试 | 自有适配器 `genesys.py`；对照 Pipecat Genesys serializer | 经 Tenant 核实后的 Audio Connector 或 SBC/SIP 桥接；被动 AudioHook 不能自动视为双向机器人接口 |
| M03 认证与准入 | 网站 Origin 与认证、Genesys 验证凭据、会话数量上限、模型任务上限 | FastAPI + `Admission` | 公网接入使用企业 IAM/短期访客令牌/反滥用网关；PoC 的手工访问凭据不作为公开网站的身份方案 |
| M04 音频标准化 | PCM16 单声道内部契约、WAV封装、状态连续的 PCMU 重采样 | Python 3.12 `audioop` + soundfile | soxr/libavcodec；升级 Python 3.13 前替换 audioop 或用 audioop-lts，并重做编码契约测试 |
| M05 VAD与终点 | 160ms 起音、640ms 静音终点、400ms 前卷、最长30s切段 | **Pipecat 0.0.102 已覆盖 Silero ONNX VAD**，Gateway封装终点；提供显式“发送当前语音”回退，自动VAD实测2/3 | Smart Turn 可减少犹豫时抢话；应先验证阿拉伯语，再增加语义终点，不能把 VAD 当成语义理解 |
| M06 ASR | 私有 multipart WAV 与 OpenRouter 专用 STT JSON 两种适配 | Qwen3-ASR 原生包装器；OpenRouter评估接口 | Nemotron 原生流式/NeMo-Speech.cpp；faster-whisper 基线。API目录可用不代表私有部署已经通过 |
| M07 回合协调 | 单会话输出所有者、epoch递增、取消旧任务、丢弃迟到音频 | `runtime.py` | Pipecat Pipeline/Frames 可覆盖更多编排能力；如整体迁入，保留统一epoch契约，避免两套回合控制同时写音频 |
| M08 业务Agent接口 | 传递会话与转录，接收回复/转人工/发音字段；业务替身用于契约测试 | 既有 HiAgent/业务平台 HTTP 接口；`DEMO_BUSINESS` 明示替身 | 自建业务Agent框架；不在Gateway重复知识库、权限与业务事务能力 |
| M09 TTS文本处理 | 180字符分句上限、保留混合语言；已实现 typed ID 逐位朗读 | `text.py` | NeMo Text Processing、CATT及业务发音词典；自动规范化/加音标可能改写专名或数字，需按字段类型验证 |
| M10 TTS | 私有 WAV、API MP3解码、统一16kHz、20ms分帧输出 | **VoxCPM2** 原生包装器；官方演示真实测试 | Chatterbox Multilingual、SILMA TTS；Kokoro只用于英语轻量对照，不覆盖阿拉伯语 |
| M11 通道控制/转人工 | 浏览器停止队列、Genesys barge_in、DTMF0、transfer请求；请求后停止AI响应 | 通道适配器与 `Session.handoff` | Genesys Architect flow 承接转接；网站人工队列系统承接。请求、平台接受、人工接通是三个不同事件 |
| M12 状态与事件 | 有界SQLite元数据事件；不存转录或音频，断线结束会话 | Python SQLite；业务长期状态由业务平台维护 | 生产用PostgreSQL/Redis及幂等键；当前不支持跨Pod恢复旧媒体队列，重连创建新会话 |
| M13 观测与评估 | 会话/事件计数、WER/CER/S-D-I、费用台账、实测结果与样本哈希 | 自有metrics/评估脚本，numpy/pytest | Prometheus/OpenTelemetry/Grafana用于生产跨实例观测；本次没有宣称已部署这些服务 |
| M14 未来Avatar Runtime | 订阅批准的语音输出、音素/时间戳与动作事件；服从同一epoch和stop | **仅接口预留，未实现** | 后续数字人专项方案。视频渲染、口型和资产许可不在本方案验收范围 |

Pipecat 在当前代码中明确复用 M05，未把其全部功能算成已实现。LiveKit Server 负责 WebRTC 房间与音视频转发，LiveKit Agents 负责语音Agent编排，与完整 Pipecat 编排有重叠。当前 WebSocket 网站加 Genesys 电话路径不依赖 LiveKit；未来多人同室、视频、共浏览或统一 WebRTC/SIP 媒体基础设施再引入媒体服务，保留一套语音回合协调器。[Pipecat](https://github.com/pipecat-ai/pipecat)、[LiveKit自托管](https://docs.livekit.io/home/self-hosting/)

网站是面向公众的入口，但通常每位访客拥有独立的“用户↔AI”会话：1000人访问对应1000个会话。转人工是该会话控制权交接；若坐席只接替AI，仍可保持两方通话。若用户、AI和坐席同时共处，则需要三方媒体能力。只有后一类需求才直接增加房间或混音要求。

## 3. 输入、输出与打断契约

内部音频统一 PCM16 little-endian、16kHz、mono。电话接入先将 PCMU 8kHz 转为内部音频；输出再转回 PCMU。升采样不能恢复电话中丢失的高频信息。浏览器保留 AEC、噪声抑制和自动增益配置，同时测耳机与扬声器两种条件。

每个会话分配随机 session_id；每次起音或停止请求增加 output epoch。旧 ASR/业务/TTS 任务即使在取消后返回，也必须校验 epoch；Gateway 发送 stop，浏览器清空排队音频，Genesys适配器发 barge_in。服务端取消和终端停止缺一不可。时序见 `diagrams/interruption.html`。

当前私有模型包装器使用整句推理，再输出20ms播放帧。这是分帧播放，**尚不是模型首音频流式推理**。后续启用 Qwen/Nemotron 流式ASR与VoxCPM2原生生成流，必须增加 partial/final、chunk序号、取消确认与迟到帧契约，不能仅换一个模型地址就宣称流式完成。

转人工请求后停止AI写音频，保存脱敏会话摘要和业务引用的责任属于业务平台。Genesys按 Architect flow 的 outputVariables.action=transfer 承接。生产应记录 handoff_requested、accepted、connected，设置超时并明确失败后的排队/结束策略；本次只有请求层协议，不能把它当成坐席已接通。[Genesys协议适配参考](https://github.com/pipecat-ai/pipecat/blob/main/src/pipecat/serializers/genesys.py)

## 4. ASR选型依据

先保留 Qwen3-ASR 1.7B 为准确率候选，0.6B为成本/延迟候选，Nemotron 3.5为流式延迟候选，随后用有授权的真实业务电话样本决定上线模型。本次统一以 OpenRouter **专用 /audio/transcriptions** 接口测试，使用同一输入与温度，不用音频聊天模型替代ASR。

20条SADA测试片段、114.04秒、3个源录音、4个方言标签；全部样本在推理前选定。每条原音频及PCMU变体分别调用三个模型，共120次成功。Qwen1.7B的归一化micro WER为原音频41.27%、PCMU51.19%；Nemotron为56.75%/68.65%；Qwen0.6B为57.14%/69.84%。Qwen1.7B响应P95约9.11s/8.27s，两个小模型约1.4–2.8s。详细结果见 [测试报告](https://github.com/baogang/dh-poc2/blob/HEAD/docs/test-report.md)。

这些是小样本和整段API结果：源录音集中、业务领域不同、训练数据重叠无法排除，不能作为沙特方言整体排名或私有流式延迟证明。当前WER与延迟不满足拟定的生产门槛。模型权重参数量不能直接推导GPU数量。Qwen3-ASR代码与权重使用Apache-2.0；Nemotron模型卡标示OpenMDW，部署时分别固定源码、权重revision和许可，不能把所有候选都写成同一种许可证。[Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR)、[Nemotron 3.5模型卡](https://huggingface.co/nvidia/Nemotron-3.5-ASR-Streaming-Multilingual-0.6b)

## 5. TTS设计、取舍与问题规避

VoxCPM2为首选评估候选：官方代码和权重标为Apache-2.0、支持阿拉伯语与原生流式生成；私有部署能控制数据路径和版本，但需要GPU及运行时验收。[VoxCPM2官方项目](https://github.com/OpenBMB/VoxCPM)

| 候选 | 适用理由 | 主要取舍与验收点 |
|---|---|---|
| VoxCPM2 | 多语言、阿拉伯语、开放代码/权重；本次官方演示6条真实合成 | 2B模型部署负担较大；演示后端revision未知；验证首音频、并发RTF、稳定音色、数字与混合语言 |
| Chatterbox Multilingual | 官方支持阿拉伯语、MIT，可作为音色/自然度对照 | 参考音频与音色授权单独核实；生成耗时、句间稳定、长句漏词和水印影响要实测，不能采用未核验社区微调 |
| SILMA TTS v1 | 150M双语Arabic/English，适合MSA低成本候选；代码MIT、权重Apache-2.0 | 阿拉伯语方言不是自动保障；规范化、加音标、vocoder等完整依赖另需验证；官方单卡RTF不代表本系统并发吞吐 |
| Kokoro82M | 轻量英语对照；OpenRouter两次真实合成 | 不覆盖阿拉伯语，本次回读发现句尾内容缺失，不能直接替代主TTS |

[Chatterbox官方项目](https://github.com/resemble-ai/chatterbox)、[SILMA模型卡](https://huggingface.co/silma-ai/silma-tts)、[Kokoro模型卡](https://huggingface.co/hexgrad/Kokoro-82M)

文本先清理控制字符、应用类型化发音策略并保留原子字段片段，再按句子与180字符上限分割。订单号/电话号按**identifier**逐位朗读；日期、金额、单位和专名按业务词典处理，不能把所有数字一律读成位数，也不能依赖模型猜测。代码已支持 speech_slots 中的 id 类型，逐位朗读片段在分句阶段保持完整，超过单片上限明确拒绝；日期/金额词典为下一阶段专门验收项。UI文字与朗读文字分别保留，便于审计。

本次 VoxCPM2 的裸数字1047回读为“عشرة إراعة سبعين”，关键ID不能判为正确；逐位文字“واحد صفر أربعة سبعة”回读完全一致。这是应采用类型化朗读的直接证据，但ASR回读包含评估ASR的误差，仍需母语听评最终判断。其余基本阿语、混合语、转接提示及英语样本回读WER为0，不等于自然度MOS为5。

| 常见问题 | 规避与验证 |
|---|---|
| 数字、姓名、地区名读错 | 类型化字段、发音词典、关键字段100%检查；日期/金额有单独正反例 |
| 流式分句破坏ID/金额 | 不在标识符内切分；先保护字段再分句；队列有界，缩短等待而非无上限积压 |
| 长句重复、漏读、幻觉或语气不稳 | 180字符上限、固定音色/seed策略、回读内容、重复次数与缺词指标；固定权重版本后回归 |
| ASR回读看似正确但听感差 | 不用WER代替MOS；至少3位阿语母语评审、盲评随机顺序、自然度/清晰度/业务可用性分项评分 |
| 8kHz电话音质下降或响度失真 | 高质量合成后正确降采样/PCMU；测削波、静音、响度及电话条件的内容保真 |
| 扬声器回声导致自问自答 | 浏览器AEC与实际扬声器测试；不要简单关闭用户麦克风，否则失去打断能力 |
| 取消后仍在播放 | output epoch + 服务端取消 + 终端队列清空；记录检测起音到最后旧音频的P95 |
| 音色克隆与数据许可混淆 | 代码、权重、数据和音色四项分别登记；本次不使用SADA说话人做克隆，公共演示采用Voice Design |

## 6. Genesys容量与私有部署

按用户确认的暂定 AHT=5分钟，Little定律：平均并发=3000/3600×300=250路；峰值系数2时500路。网站并发另计，不能包含在电话数字里。

| AHT | 平均并发 | 两倍峰值并发 |
|---|---:|---:|
| 3分钟 | 150 | 300 |
| 5分钟 | 250 | 500 |
| 10分钟 | 500 | 1000 |

若**假设**ASR活跃占比35%、TTS25%，500路对应175路/125路活跃等效负载。它们是待业务采样校正的占比；ASR可能必须持续监听，流式缓存与每会话显存不能按占比忽略。部署图见 `diagrams/deployment.html`。

生产分为入口认证/TLS、可横向扩展Gateway、独立ASR池、独立TTS池、业务平台与状态观测。持久WebSocket自然绑定当前Pod；滚动发布先停止准入、排空既有会话，不能直接迁移进程内VAD状态。共享业务状态保持幂等；断线不重放旧声音。当前PoC用一个Gateway、SQLite和每类一个模型进程，默认20路/4模型任务，**不是500路生产配置**。

先用目标GPU跑压测，得到符合延迟门槛时的有效并发 C_asr/C_tts。示例公式为 ceil(175/(C_asr×0.65)) 与 ceil(125/(C_tts×0.65))，再增加故障余量；0.65是拟定利用率目标。若实测 C_asr=20、C_tts=25，示例分别14/8张加余量；这两个C是算例，不是本次硬件测量或采购建议。流式会话显存、峰值重叠和单节点故障可能使按活跃等效计算低估，须以500路完整回合压测为准。

PCMU双向原始音频在500路时约64Mbit/s，不含WebSocket/TLS、网络包与复制开销；每100路网站16kHz PCM16双向约51.2Mbit/s。采集连接、排队等待和输出缓冲也消耗CPU/RAM，应监控队列、超时、显存及GPU饱和；达到上限明确拒绝或转人工，不无限排队。

运行时模型不访问OpenRouter或公共演示。权重离线导入、固定revision/哈希，模型服务只在内网开放；公网仅暴露经过认证的入口。`compose.yaml`和原生服务封装提供基础路径；CPU Gateway镜像已经实际构建，CUDA目标环境仍需执行模型加载、单路回合及持续压测。Genesys产品版本、双向接口许可、HMAC认证、媒体格式和Architect转接流程必须在Tenant对接时确认。

## 7. 测试指标、准确率与验收计划

ASR使用micro WER=(S+D+I)/N，同时报告CER、原始严格WER、方言/噪声/编码切片、关键字段准确率和空音频幻觉率。WER可超过100%，因此不把1-WER叫业务准确率。归一化规则固定，不删除英文、数字或重要字段。测试集不得用于挑选提示、词典或微调后仍冒充独立验收集。

TTS分开测内容与听感：内容回读WER只是代理指标，另将订单号、日期、金额映射成标准字段做exact-match；母语听评测自然度、清晰度与发音。测TTFA、句间间隔、RTF、削波/静音、漏词/重复及取消残留。当前报告只有合成和自动回读，没有人工MOS。

端到端业务准确率定义为**完整会话最终完成正确业务目标的比例**，分母包含转录错误、业务错误、TTS关键字段错误、工具失败与转接失败；正确澄清/拒绝也按预先标注的目标评分。多轮测试由真实用户话音、授权业务数据与预先标注的终态组成，业务平台和客服平台共同提供结果证据。不能把ASR准确率×TTS准确率当成端到端准确率。

转人工/澄清等决策分别建立TP/FP/FN/TN：Precision=TP/(TP+FP)，Recall=TP/(TP+FN)，误触发率=FP/(FP+TN)。报告分母和95%区间，并区分人工请求识别、请求被平台接受、坐席接通。业务替身的单元测试通过不能说明真实任务成功率或真实召回率。

拟定上线门槛：关键ID/金额回读与业务校验100%；转人工Recall≥95%且误触发≤2%；业务任务成功≥90%；母语MOS≥4/5；正常负载回合P95首音频≤1.5s、打断旧声音P95≤350ms。阈值需按业务场景和可达硬件共同批准，本次未宣称满足。

验收依次进行：①小样本功能与接口回归；②源节目/说话人隔离的授权业务盲测，电话/网站/噪声/混合语分层；③Genesys实联与坐席转接；④目标GPU的逐级负载、3000calls/h到达率、500并发及AHT敏感性；⑤持续运行、故障注入、Pod排空、弱网、回声与重连；⑥冻结模型/词典/依赖后复测。压测使用300s会话与真实回合占比，不用500个瞬时HTTP请求替代500路语音通话。

参考数据来自聊天“分析语音数据集用途”中的 SADA/Sada2022；官方数据许可为CC BY-NC-SA4.0。该广播语音集用于非商业研究对照，不自动授权商用微调。8kHz变体是人工电话编码劣化，非Genesys真实录音。未来使用经授权的电话业务集作最终验收，并登记隐私、保留策略与来源。[SADA官方](https://www.kaggle.com/datasets/sdaiancai/sada2022)、[固定镜像revision](https://huggingface.co/datasets/khaledalganem/sada2022/tree/f45d9ad8e60aa3613229322e0712eb5874ff94f6)

## 8. 实施决策与交付索引

推荐批准“可私有部署的模块边界与PoC验证路径”，保留Qwen1.7B、Nemotron3.5及VoxCPM2作为进一步业务评估候选。模型最终选定、生产容量和准确率签署以第7节验收证据为依据。本次不建议凭20条SADA样本冻结生产模型或GPU数量。

代码：[baogang/dh-poc2](https://github.com/baogang/dh-poc2)。[方案源码](https://github.com/baogang/dh-poc2/blob/HEAD/docs/solution.md)、[测试报告](https://github.com/baogang/dh-poc2/blob/HEAD/docs/test-report.md)、[独立Review与逐项修复](https://github.com/baogang/dh-poc2/blob/HEAD/docs/review.md)均保存在仓库docs；评估音频/转录/凭据不进入公开仓库。后续DH增加M14以及必要媒体能力，沿用session_id、epoch、时间戳和handoff契约，可保留ASR/TTS服务与业务接口。
