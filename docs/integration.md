# 集成与复现契约

网站 `/ws/website`：Origin必须在允许列表；连接后5秒内发送 `{"type":"auth","token":"..."}`，收到ready后发送PCM16 mono/16kHz帧。客户端不能把永久共享凭据嵌入公开网页；上线应由入口换取短期会话凭据。本PoC手工凭据只用于受控验证。

服务端 `audio` JSON标头携带epoch/sample_rate，紧随一个二进制PCM帧；stop立即清空播放队列。浏览器播放积压超过500ms主动停止。ping每15秒，45秒无消息或最长10分钟关闭会话。

Genesys `/ws/genesys`：当前适配v2格式，协商PCMU 8000 external mono，只支持这一媒体组合；无open的二进制帧、重复seq、不同id、L16/BOTH均拒绝。PoC入口为独立Bearer凭据门，生产需在受信入口完成Genesys签名/HMAC校验并移除客户端伪造认证头；不得直接把PoC地址配置成未经核实的生产双向接口。

业务接口请求 `{"session_id":"...","text":"...","locale":"ar-SA"}`；响应 `{"reply":"...","handoff":false,"reason":"...","speech_slots":[{"kind":"id","value":"1047"}]}`。Agent adapter应把业务会话/工具幂等与授权纳入已有平台，PoC没有实现真实业务工具。本次reply与UI保持原文，TTS按id类型生成逐位朗读。日期、金额和专名需业务词典；不接受任意SSML。

转人工这里只发送请求。电话需要Architect flow承接transfer，网站需要人工队列服务。Gateway请求后阻止后续AI回复；平台仍应确认accepted/connected与失败终态。当前无人工聊天UI、坐席桥接或跨Pod恢复。

私有模型端点遵循 `/v1/audio/transcriptions` multipart(WAV、model、language)与 `/v1/audio/speech` JSON(model、input、voice、response_format)。TTS私有包装器只接受default/wav；Gateway解码真实采样率并转内部16kHz。OpenRouter使用JSON input_audio与speech MP3；认证信息仅发配置的模型服务，不自动探测账户。

复现数据固定镜像revision、split=test、方言过滤、长度3–12s、至少6词、Clean标签、每方言首个合格源文件取前六条；实际为Najdi3、Hijazi6、Khaliji6、MSA5，共20条。选择逻辑与音频hash可追溯；源文件之间方言混用，不能把20条当20个独立节目。
