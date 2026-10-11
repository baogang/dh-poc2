"""M04: stateful PCMU transcoding; PCM16 mono is the internal audio contract."""
import audioop
import io
import wave


def wav_bytes(pcm: bytes, rate: int = 16000) -> bytes:
    if len(pcm) % 2:
        raise ValueError("unaligned PCM16")
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return out.getvalue()


class PCMUCodec:
    def __init__(self):
        self.input_state = None
        self.output_state = None

    def decode(self, data: bytes) -> bytes:
        pcm = audioop.ulaw2lin(data, 2)
        pcm, self.input_state = audioop.ratecv(pcm, 2, 1, 8000, 16000, self.input_state)
        return pcm

    def encode(self, data: bytes, rate: int = 16000) -> bytes:
        pcm, self.output_state = audioop.ratecv(data, 2, 1, rate, 8000, self.output_state)
        return audioop.lin2ulaw(pcm, 2)


def telephone_wav(pcm: bytes) -> bytes:
    """One PCMU round trip; a controlled degradation, not a real phone capture."""
    codec = PCMUCodec()
    return wav_bytes(codec.decode(codec.encode(pcm)))
