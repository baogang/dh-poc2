"""M05: real Pipecat Silero ONNX VAD. No amplitude threshold as speech proof."""
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams, VADState
import audioop


class TurnVAD:
    def __init__(self):
        self.model = SileroVADAnalyzer(sample_rate=16000,
            params=VADParams(confidence=.7, start_secs=.16, stop_secs=.64, min_volume=.3))
        self.model.set_sample_rate(16000)
        self.previous = VADState.QUIET
        self.active = False
        self.audio = bytearray()
        self.preroll = bytearray()
        self.manual_buffer = bytearray()

    async def feed(self, data):
        self.manual_buffer.extend(data)
        del self.manual_buffer[:-960000]  # explicit fallback keeps at most 30s.
        state = await self.model.analyze_audio(data)
        start = state == VADState.SPEAKING and not self.active
        if start:
            self.active = True
            self.audio.extend(self.preroll)
        if self.active:
            self.audio.extend(data)
        else:
            self.preroll.extend(data)
            del self.preroll[:-12800]  # 400ms to preserve onset.
        utterance = None
        if self.active and (state == VADState.QUIET or len(self.audio) >= 960000):
            utterance = bytes(self.audio)
            self.audio.clear()
            self.preroll.clear()
            self.active = False
            self.manual_buffer.clear()
        self.previous = state
        return start, utterance

    def manual(self):
        """Explicit website submit when VAD misses speech; never auto-submit noise."""
        data = bytes(self.manual_buffer)
        self.manual_buffer.clear()
        if len(data) < 3200 or audioop.rms(data, 2) < 80:
            return None
        self.audio.clear()
        self.preroll.clear()
        self.active = False
        self.model.set_params(self.model.params)
        return data

    def close(self):
        # Pinned Pipecat 0.0.102 has no public analyzer close method.
        self.model._executor.shutdown(wait=False, cancel_futures=True)
