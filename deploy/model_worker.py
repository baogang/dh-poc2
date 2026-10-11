"""Native OSS service contract; offline staged weights, single model per process.

GPU runtime must be smoke-tested on the target Linux/CUDA host before admission.
This file deliberately does not download arbitrary remote URLs or cloned voices.
"""
import io
import os
import secrets
import threading
from pathlib import Path
import numpy as np
import soundfile as sf
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

app=FastAPI()
kind=os.getenv('WORKER','asr')
token=os.environ['MODEL_API_KEY']
if len(token)<32:raise RuntimeError('MODEL_API_KEY must contain at least 32 characters')
model_dir=os.getenv('MODEL_DIR','/models')
if not Path(model_dir).is_dir():raise RuntimeError('stage verified model snapshot before startup')
lock=threading.Lock()
model=None


def authenticate(request):
    if not secrets.compare_digest(request.headers.get('authorization',''),'Bearer '+token):
        raise HTTPException(401)


@app.on_event('startup')
def load():
    global model
    import torch
    if kind=='asr':
        from qwen_asr import Qwen3ASRModel
        model=Qwen3ASRModel.from_pretrained(model_dir,dtype=torch.bfloat16,device_map='cuda:0',
            max_inference_batch_size=1,max_new_tokens=512)
    elif kind=='tts':
        from voxcpm import VoxCPM
        model=VoxCPM.from_pretrained(model_dir,local_files_only=True,load_denoiser=False,optimize=False,device='cuda')
    else:raise RuntimeError('unknown worker kind')


@app.get('/health')
def health():return {'ready':model is not None,'kind':kind}


@app.post('/v1/audio/transcriptions')
def transcribe(request: Request,file: UploadFile=File(...),language: str=Form('ar'),model_id: str=Form('',alias='model')):
    authenticate(request)
    if kind!='asr':raise HTTPException(404)
    data=file.file.read(2_000_001)
    if len(data)>2_000_000:raise HTTPException(413)
    try:
        audio,rate=sf.read(io.BytesIO(data),dtype='float32',always_2d=True)
        if len(audio)/rate>30 or not np.isfinite(audio).all():raise ValueError()
    except Exception:raise HTTPException(400,'invalid audio')
    if not lock.acquire(blocking=False):raise HTTPException(429,'worker busy')
    try:
        result=model.transcribe(audio=(audio.mean(axis=1),rate),language={'ar':'Arabic','en':'English'}.get(language))
        return {'text':result[0].text}
    finally:lock.release()


class Speech(BaseModel):
    input: str=Field(min_length=1,max_length=180)
    model: str=''
    voice: str='default'
    response_format: str='wav'


@app.post('/v1/audio/speech')
def speak(request: Request,body: Speech):
    authenticate(request)
    if kind!='tts':raise HTTPException(404)
    if body.response_format!='wav' or body.voice!='default':raise HTTPException(400,'only WAV/default voice in this PoC')
    if not lock.acquire(blocking=False):raise HTTPException(429,'worker busy')
    try:
        audio=model.generate(text=body.input,normalize=False,denoise=False,seed=42,
            retry_badcase_max_times=1,max_len=1024)
        rate=model.tts_model.sample_rate
        if len(audio)/rate>60:raise HTTPException(413,'generated audio too long')
        out=io.BytesIO();sf.write(out,audio,rate,format='WAV',subtype='PCM_16')
        return Response(out.getvalue(),media_type='audio/wav')
    finally:lock.release()
