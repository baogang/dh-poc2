# 第三方代码、权重、数据与音色登记

本项目使用依赖而不复制其权重或训练语料。各组件保留原许可；代码许可不能代替模型、数据或音色授权。

| 对象 | 官方许可/来源 | 使用范围 |
|---|---|---|
| Pipecat | BSD-2-Clause，https://github.com/pipecat-ai/pipecat/blob/main/LICENSE | 固定0.0.102，复用Silero VAD |
| Silero VAD | MIT，https://github.com/snakers4/silero-vad | Pipecat内置ONNX权重；版本随其wheel固定 |
| Qwen3-ASR | Apache-2.0，https://github.com/QwenLM/Qwen3-ASR | 代码固定提交；权重私有导入需revision及hash |
| Nemotron3.5 ASR | 官方模型卡指定OpenMDW，https://huggingface.co/nvidia/Nemotron-3.5-ASR-Streaming-Multilingual-0.6b | OpenRouter测试；部署时按实际snapshot许可登记 |
| VoxCPM2 | Apache-2.0代码/权重，https://github.com/OpenBMB/VoxCPM | 代码固定提交，公共官方演示测试；私有权重单独导入 |
| Chatterbox | MIT，https://github.com/resemble-ai/chatterbox | 备选，未声称本机测试通过 |
| SILMA TTS | 代码MIT、权重Apache-2.0，https://huggingface.co/silma-ai/silma-tts | 备选；参考音色不得从SADA直接克隆 |
| Kokoro82M | Apache-2.0权重，https://huggingface.co/hexgrad/Kokoro-82M | 英语API对照，音色权利另核实 |
| SADA/Sada2022 | CC BY-NC-SA4.0，SDAIA/NCAI与SBA；https://www.kaggle.com/datasets/sdaiancai/sada2022 | 非商业研究测试；音频、原始/衍生转录不上传仓库，未作为商用训练许可 |
| 原创TTS测试文本 | 项目测试作者编写，无个人敏感信息 | 公开演示Voice Design，不提供或克隆真人参考音频 |

OpenRouter只是评估通路，其模型目录和API成功调用不构成权重私有部署许可或业务数据留存承诺。生产路径仅访问私有模型服务。
