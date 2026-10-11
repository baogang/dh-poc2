# ASR/TTS 集成方案 PoC

面向网站语音和 Genesys 接入的 Speech Gateway。实现可替换的 ASR/TTS HTTP 接口、真实 Pipecat/Silero VAD、会话隔离、PCMU 转码、打断、输出代次校验、限流和转人工请求。业务 Agent 当前为明确标识的契约测试替身，外部业务服务可通过配置接入。Avatar Runtime 仅预留，不包含在实现中。

## 本机运行

需要 Python 3.12；公网网站应使用 HTTPS/WSS。当前网站验证入口传输 PCM16/16kHz 单声道，启用浏览器 AEC。默认不启用 LiveKit。

```sh
python3.12 -m venv .venv
.venv/bin/pip install -e '.[test]'
cp .env.example .env
```

编辑 `.env`：分别配置至少 32 字符随机 `GATEWAY_TOKEN`、`GENESYS_TOKEN` 和私有模型端点；不要复用临时测试 Key。`MODEL_API_KEY` 为本地模型服务凭据。`DEMO_BUSINESS=true` 只能用于验证，不代表业务任务准确率。`BUSINESS_URL` 的契约见 [集成说明](docs/integration.md)。

```sh
.venv/bin/uvicorn speech_gateway.server:create_app --factory --env-file .env --host 127.0.0.1 --port 8080 --workers 1 --ws-max-size 32768 --ws-max-queue 4
.venv/bin/pytest -q
# 客户端重连回归需要 Node.js；缺少 Node 时该项标为 skipped。
```

打开 `http://localhost:8080`，输入当前验证环境的 gateway 凭据、点击开始并允许麦克风。首次建议用耳机验证，随后专门做扬声器回声测试。多人可同时使用入口，每位访客分配独立会话。

## 私有模型部署

提供 `compose.yaml`、两个独立 GPU 镜像和 `deploy/model_worker.py`。模型权重需先固定 HF snapshot revision 并下载到 `models/qwen-asr`、`models/voxcpm2`，保存文件 SHA256 清单。上线运行使用离线只读挂载。构建阶段有依赖下载，运行阶段服务网络为内部网络。两台 GPU 的验证配置使用设备 0/1，可按目标设备调整。当前本机是 Intel macOS，未运行 CUDA 镜像；目标 Linux/NVIDIA 环境的加载、合成和容量验收是部署步骤，报告不会将公共 API 结果当成本地部署成绩。

```sh
docker compose --env-file .env config --quiet
docker compose build
docker compose up -d
```

ASR 原生封装固定 Qwen3-ASR 源码提交，TTS 原生封装固定 VoxCPM 源码提交。暂用整句 WAV 接口，模型生成完成后按 20ms 音频帧播放；不能宣称已实现模型首音频流式输出。模型接口保持可替换；后续切换原生流式或 vLLM-Omni 需要增加 chunk/cancel 契约测试。

## 真实评估

```sh
python scripts/prepare_sada.py
python scripts/evaluate_openrouter.py
python scripts/evaluate_voxcpm.py
python scripts/evaluate_tts_content.py
```

OpenRouter 凭据通过隐藏交互输入；脚本不读账户资料。所有付费脚本复用 artifacts/raw/cost.json，累计预算 5 美元。请求发出前用文件锁、原子替换和 fsync 持久化唯一 call_id；超时/取消仍保留占用。结果不能覆盖；ASR 重测可使用新 --run-dir，但必须继续使用同一 --ledger，不能通过新目录重置累计预算。SADA 原始音频与转录仅保存在忽略的 `data/`、`artifacts/raw/`，不上传公开仓库。它是 CC BY-NC-SA 4.0 研究数据，不能直接当成商用训练授权。公开报告只保留聚合指标、样本 ID、音频哈希和复现方法。

VoxCPM2 公开演示用于真实 TTS 内容测试，不需要任何 Key；演示版本可追溯但后端权重 revision 未公开。不得将演示速度视为私有 GPU 吞吐。真实 Genesys Tenant、业务平台和母语听评另有验收门槛，见方案和测试报告。
