"""Real Silero -> OpenRouter Qwen ASR -> demo business -> official VoxCPM2 TTS.

Not live Genesys, microphone capture, business acceptance or production capacity.
"""
import asyncio
import getpass
import io
import json
import sys
import time
from pathlib import Path
import httpx
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from evaluate_openrouter import Budget
from evaluate_voxcpm import synthesize
from speech_gateway.config import Settings
from speech_gateway.providers import HTTPProviders
from speech_gateway.runtime import Session
from speech_gateway.vad import TurnVAD
from speech_gateway.journal import Journal


async def main():
    key=getpass.getpass('OpenRouter temporary key (hidden): ')
    root=Path('artifacts/raw');budget=Budget(root/'cost.json')
    if (root/'real-pipeline.json').exists():
        raise RuntimeError('Existing pipeline evidence: preserve results and shared ledger')
    settings=Settings('w'*32,'g'*32,asr_url='https://openrouter.ai/api/v1',api_key=key,asr_model='qwen/qwen3-asr-1.7b')
    class Real(HTTPProviders):
        async def asr(self,wav):
            call_id=budget.reserve(.02, settings.asr_model)
            text=await super().asr(wav)
            budget.settle(call_id,{})
            return text
        async def tts(self,text):
            async with httpx.AsyncClient(timeout=150) as c:data=await synthesize(c,text)
            a,rate=sf.read(io.BytesIO(data),dtype='float32',always_2d=True)
            from math import gcd
            g=gcd(rate,16000);a=resample_poly(a.mean(axis=1),16000//g,rate//g)
            return (np.clip(a,-1,1)*32767).astype('<i2').tobytes()
    p=Real(settings);rows=[]
    manifest=json.loads(Path('data/sada/manifest.json').read_text())['samples']
    for sample in manifest[:3]:
        vad=TurnVAD();j=Journal(':memory:');events=[];frames=[];first=None;t0=time.perf_counter()
        async def send(e):events.append(e['type'])
        async def audio(a,e):
            nonlocal first
            if first is None:first=time.perf_counter()
            frames.append(a)
        s=Session(sample['id'],p,send,audio,j,asyncio.Semaphore(1));utterances=0
        a,rate=sf.read(sample['audio']['clean'],dtype='int16');pcm=a.astype('<i2').tobytes()+b'\x00'*32000
        for pos in range(0,len(pcm),640):
            start,turn=await vad.feed(pcm[pos:pos+640])
            if start:await s.interrupt()
            if turn:
                utterances+=1;await s.submit(turn)
        manual=False
        if not utterances:
            turn=vad.manual()
            if turn:
                manual=True;await s.submit(turn)
        if s.task:await s.task
        row={'id':sample['id'],'vad_utterances':utterances,'manual_submit_fallback':manual,'events':events,'output_frames':len(frames),
             'first_output_seconds_from_fast_injection_start':first-t0 if first else None,
             'pipeline_completed':bool(frames) and 'done' in events,'business':'demo contract double'}
        rows.append(row);print(json.dumps(row),flush=True)
        await s.close();vad.close();j.close()
    await p.close();(root/'real-pipeline.json').write_text(json.dumps(rows,indent=2))

if __name__=='__main__':asyncio.run(main())
