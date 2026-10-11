import io
import httpx
import numpy as np
import pytest
import soundfile as sf
from speech_gateway.providers import HTTPProviders
from speech_gateway.config import Settings


async def test_private_asr_and_tts_contracts():
    seen=[]
    def handler(r):
        seen.append(r)
        if r.url.path.endswith('transcriptions'):return httpx.Response(200,json={'text':'مرحبا'})
        b=io.BytesIO();sf.write(b,np.zeros(2400),24000,format='WAV')
        return httpx.Response(200,content=b.getvalue())
    p=HTTPProviders(Settings('w'*32,'g'*32),httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await p.asr(b'RIFF')=='مرحبا'
    assert len(await p.tts('مرحبا'))==3200
    assert 'multipart/form-data' in seen[0].headers['content-type']
    await p.close()


async def test_openrouter_dedicated_stt_not_chat_completions():
    def handler(r):
        assert r.url.path=='/api/v1/audio/transcriptions'
        assert b'input_audio' in r.content and b'file' not in r.content
        return httpx.Response(200,json={'text':'مرحبا'})
    s=Settings('w'*32,'g'*32,asr_url='https://openrouter.ai/api/v1')
    p=HTTPProviders(s,httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await p.asr(b'RIFF')=='مرحبا'
    await p.close()


async def test_invalid_model_response_and_business_contract():
    p=HTTPProviders(Settings('w'*32,'g'*32),httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'text':123}))))
    with pytest.raises(ValueError):await p.asr(b'RIFF')
    await p.close()
