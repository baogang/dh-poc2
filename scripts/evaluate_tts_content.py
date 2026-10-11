"""Continue the shared USD5 budget: MP3 API retry and selected OSS TTS read-back."""
import asyncio
import base64
import getpass
import hashlib
import io
import json
import time
from pathlib import Path
import httpx
import soundfile as sf
from evaluate_openrouter import Budget, TTS_CASES, MODELS
from speech_gateway.metrics import score


async def main():
    key=getpass.getpass('OpenRouter temporary key (hidden): ')
    root=Path('artifacts/raw');budget=Budget(root/'cost.json')
    if (root/'tts-retry.json').exists() or (root/'tts-content.json').exists():
        raise RuntimeError('Existing continuation results; preserve the shared ledger and results')
    results=[]
    async with httpx.AsyncClient(timeout=60) as c:
        headers={'Authorization':'Bearer '+key}
        for model,voice in [('hexgrad/kokoro-82m','af_heart'),('qwen/qwen-audio-3.0-tts-flash','Cherry')]:
            for cid,text in TTS_CASES:
                if model.startswith('hexgrad') and cid.startswith('ar_'):continue
                call_id=budget.reserve(.1, model);start=time.perf_counter()
                r=await c.post('https://openrouter.ai/api/v1/audio/speech',headers=headers,json={
                    'model':model,'input':text,'voice':voice,'response_format':'mp3'})
                item={'model':model,'case':cid,'input':text,'status':r.status_code,'response_format':'mp3'}
                if r.is_success:
                    a,sr=sf.read(io.BytesIO(r.content),always_2d=True);p=root/(model.split('/')[1]+'-'+cid+'.mp3');p.write_bytes(r.content)
                    item.update(path=str(p),duration=len(a)/sr,sample_rate=sr,sha256=hashlib.sha256(r.content).hexdigest())
                else:
                    err=r.json().get('error',{});item['error']=str(err.get('message','http_failure')).replace(key,'[REDACTED]')[:400]
                item['elapsed_seconds']=time.perf_counter()-start
                budget.settle(call_id,{});results.append(item)
                (root/'tts-retry.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
                print(model,cid,item.get('status'),item.get('error'),flush=True)
        native=json.loads((root/'voxcpm2.json').read_text())
        content=[]
        for item in native+results:
            if not item.get('path'):continue
            audio,rate=sf.read(item['path'],always_2d=True);b=io.BytesIO();sf.write(b,audio,rate,format='WAV',subtype='PCM_16')
            call_id=budget.reserve(.02, MODELS[0]);start=time.perf_counter()
            r=await c.post('https://openrouter.ai/api/v1/audio/transcriptions',headers=headers,json={
                'model':MODELS[0],'input_audio':{'data':base64.b64encode(b.getvalue()).decode(),'format':'wav'},
                'language':'en' if item['case'].startswith('en_') else 'ar','temperature':0})
            row={'model':item['model'],'case':item['case'],'status':r.status_code,'duration':item['duration']}
            body=r.json();usage=body.get('usage',{})
            if r.is_success:row.update(hypothesis=body['text'],scores=score(item['input'],body['text']))
            row['elapsed_seconds']=time.perf_counter()-start;content.append(row);budget.settle(call_id,usage)
            (root/'tts-content.json').write_text(json.dumps(content,ensure_ascii=False,indent=2))
            print('READBACK',row['model'],row['case'],row.get('scores',{}).get('wer',{}).get('error_rate'),flush=True)
    print('Budget:', {k:v for k,v in budget.snapshot().items() if k != 'calls'})

if __name__=='__main__':asyncio.run(main())
