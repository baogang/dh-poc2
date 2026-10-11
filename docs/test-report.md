# ASR/TTS PoC 测试报告

执行日期：2026-10-12。Intel macOS / Python 3.12；API结果不代表本机GPU部署。

## ASR真实测试

SADA test划分固定20条（114.04秒、252个归一化参考词），3个源录音；Hijazi6/Khaliji6/ModernStandardArabic5/Najdi3。
当前ASR结果：成功120次 / 请求120次；失败0次。

| 模型 | 条件 | 成功/请求 | micro WER | CER | API响应P50/P95秒 |
|---|---|---:|---:|---:|---:|
| nvidia/nemotron-3.5-asr-streaming-multilingual-0.6b | clean | 20/20 | 56.75% | 26.22% | 1.61/2.79 |
| nvidia/nemotron-3.5-asr-streaming-multilingual-0.6b | pcmu | 20/20 | 68.65% | 41.58% | 1.41/2.11 |
| qwen/qwen3-asr-0.6b | clean | 20/20 | 57.14% | 28.32% | 0.83/1.37 |
| qwen/qwen3-asr-0.6b | pcmu | 20/20 | 69.84% | 37.59% | 1.02/1.72 |
| qwen/qwen3-asr-1.7b | clean | 20/20 | 41.27% | 19.44% | 3.85/9.11 |
| qwen/qwen3-asr-1.7b | pcmu | 20/20 | 51.19% | 27.82% | 4.17/8.27 |

原音频中，本次取得结果的最低WER为 qwen/qwen3-asr-1.7b。这是有限样本的描述，不是生产排名。

样本集中于少量方言/节目/说话人；未挑除错误样本、未微调。PCMU变体是人工编码劣化，不是Genesys录音。归一化保留数字英文；严格WER及S/D/I可从本地原始结果复算。

## TTS真实测试

VoxCPM2官方Nano-vLLM演示成功6/6条原创文本。源码revision见公开JSON，后端权重revision未公开；零参考音频Voice Design，没有克隆SADA说话人。
全响应耗时2.85–3.85秒，生成音频4.03–5.95秒。不是TTFA或私有GPU吞吐。
OpenRouter 初次WAV请求 / hexgrad/kokoro-82m：成功0/2，HTTP状态{'400': 2}。
OpenRouter 初次WAV请求 / qwen/qwen-audio-3.0-tts-flash：成功0/5，HTTP状态{'400': 5}。
OpenRouter MP3重试 / hexgrad/kokoro-82m：成功2/2，HTTP状态{'200': 2}。
OpenRouter MP3重试 / qwen/qwen-audio-3.0-tts-flash：成功0/5，HTTP状态{'400': 5}。

| 模型/案例 | 合成回读WER | 判断 |
|---|---:|---|
| VoxCPM2 official Nano-vLLM demo / ar_basic | 0.00% | 内容代理指标，不等于母语MOS |
| VoxCPM2 official Nano-vLLM demo / ar_digits | 71.43% | 裸数字存在回读错误；关键ID需逐位朗读和专门验收 |
| VoxCPM2 official Nano-vLLM demo / ar_spoken_digits | 0.00% | 内容代理指标，不等于母语MOS |
| VoxCPM2 official Nano-vLLM demo / ar_mixed | 0.00% | 内容代理指标，不等于母语MOS |
| VoxCPM2 official Nano-vLLM demo / ar_handoff | 0.00% | 内容代理指标，不等于母语MOS |
| VoxCPM2 official Nano-vLLM demo / en_basic | 0.00% | 内容代理指标，不等于母语MOS |
| hexgrad/kokoro-82m / en_basic | 50.00% | 内容代理指标，不等于母语MOS |
| hexgrad/kokoro-82m / en_number | 63.64% | 内容代理指标，不等于母语MOS |

回读使用ASR作为内容代理，ASR自身可能出错；不能代替母语听评。类型化ID逐位朗读已实现，并在分句阶段保持原子片段；日期、金额和专名需要业务发音词典。单个成功案例不能证明所有数字已解决。

## 真实集成串联与控制测试

Silero VAD→Qwen ASR→业务契约替身→官方VoxCPM2，快速注入3条；串联完成3条，自动VAD产生回合2条，显式发送回退1条。未经过真实麦克风或Genesys。

| 样本 | VAD回合 | 显式发送回退 | 输出帧 | 串联完成 |
|---|---:|---|---:|---|
| 6k_SBA_113_0-seg_254_890-258_010 | 0 | True | 122 | True |
| 6k_SBA_113_0-seg_268_500-272_470 | 1 | False | 122 | True |
| 6k_SBA_113_0-seg_404_260-413_630 | 1 | False | 178 | True |

串联完成只指音频返回，业务为替身；不报告真实业务准确率、转人工召回或MOS。VAD遗漏保留为限制，显式发送不算自动VAD成功。

单元、协议、失败路径与客户端重连测试的实际命令、数量和独立复核见 [Review记录](review.md)。CUDA模型加载和吞吐尚未实测。三个diagram-design HTML已自检和浏览器预览。

## 费用、来源与数据保护

CPU Gateway镜像 sha256:d9e28e167839067c40b98ce405693e2121454417df3405c1bf70f7cb95f55e34，Compose配置退出码0，健康ok，网站True；WebSocket准入检查{'attempted': 30, 'accepted': 20, 'capacity_rejected': 10, 'models_called': 0}，断线后会话0。该检查未调用模型，不代表GPU/业务/500路生产压测。
授权累计上限 $5.00。接口回传费用 $0.003475；19次费用未知/预留，记账占用 $1.503475。未读账户/余额；预留不是已核对账单。付费请求前持久化唯一call_id，异常仍占用预算；全部批次复用同一台账。

凭据只隐藏输入并发到OpenRouter，不写入代码、结果、报告或GitHub。SADA音频/转录保存在忽略路径；公开JSON只有样本ID、hash、聚合指标和原创TTS文本。SADA CC BY-NC-SA4.0仅作非商业研究测试。

## 当前验收结论

本报告记录已执行部分与失败，未执行不计通过。当前小样本WER、响应时延、关键数字与VAD反例不能支持生产质量达标。下一阶段须做授权业务盲测、母语听评、Genesys实联、目标CUDA加载和3000calls/h/500路真实回合压测；模拟结果不能替代。
