import pytest
from speech_gateway.vad import TurnVAD


async def test_real_silero_silence_and_bounded_manual_buffer():
    vad=TurnVAD()
    try:
        start,utterance=await vad.feed(b'\x00'*32000)
        assert not start and utterance is None and vad.manual() is None
        # Large explicit capture is bounded independently of automatic VAD buffer.
        vad.manual_buffer.extend(b'\x01\x01'*500000)
        await vad.feed(b'\x00'*640)
        assert len(vad.manual_buffer)<=960000
        assert len(vad.manual())<=960000
    finally:vad.close()
