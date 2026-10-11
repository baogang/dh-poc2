"""M06/M08/M10: private HTTP providers and explicit OpenRouter evaluation mode."""
import base64
import io
import httpx
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from .text import chunks


class HTTPProviders:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=httpx.Timeout(40, connect=5))

    def headers(self):
        return {"Authorization": "Bearer "+self.settings.api_key} if self.settings.api_key else {}

    async def asr(self, wav: bytes) -> str:
        s = self.settings
        if "openrouter.ai" in s.asr_url:
            r = await self.client.post(s.asr_url+"/audio/transcriptions", headers=self.headers(), json={
                "model": s.asr_model, "input_audio": {"data": base64.b64encode(wav).decode(), "format": "wav"}, "language": "ar", "temperature": 0})
        else:
            r = await self.client.post(s.asr_url+"/audio/transcriptions", headers=self.headers(),
                data={"model": s.asr_model, "language": "ar"}, files={"file": ("turn.wav", wav, "audio/wav")})
        r.raise_for_status()
        text = r.json().get("text")
        if not isinstance(text, str) or len(text) > 8000:
            raise ValueError("invalid transcript response")
        return text.strip()

    async def business(self, session_id, text) -> dict:
        s = self.settings
        if s.demo_business:
            # Contract test double, not an operational citizen-service agent.
            transfer = any(w in text for w in ["موظف", "إنسان", "agent", "human"])
            return {"reply": "سأحولك إلى موظف خدمة العملاء." if transfer else "يرجى توضيح الخدمة المطلوبة.",
                    "handoff": transfer, "reason": "user_requested" if transfer else "demo_clarification"}
        r = await self.client.post(s.business_url, headers={"Authorization": "Bearer "+s.business_token},
            json={"session_id": session_id, "text": text, "locale": "ar-SA"})
        r.raise_for_status()
        d = r.json()
        if not isinstance(d.get("reply"), str) or not isinstance(d.get("handoff"), bool):
            raise ValueError("invalid business contract")
        return d

    async def tts(self, text: str) -> bytes:
        s = self.settings
        r = await self.client.post(s.tts_url+"/audio/speech", headers=self.headers(),
            json={"model": s.tts_model, "input": text, "voice": s.voice,
                  "response_format": "mp3" if "openrouter.ai" in s.tts_url else "wav"})
        r.raise_for_status()
        if len(r.content) > 8_000_000:
            raise ValueError("TTS audio exceeds response limit")
        audio, rate = sf.read(io.BytesIO(r.content), dtype="float32", always_2d=True)
        if not np.isfinite(audio).all() or rate < 8000 or rate > 96000 or len(audio)/rate > 60:
            raise ValueError("invalid TTS waveform")
        mono = audio.mean(axis=1)
        if rate != 16000:
            from math import gcd
            g = gcd(rate, 16000)
            mono = resample_poly(mono, 16000//g, rate//g)
        return (np.clip(mono, -1, 1)*32767).astype("<i2").tobytes()

    async def close(self):
        await self.client.aclose()
