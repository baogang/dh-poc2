"""Selected OSS TTS real test on the official public demo; no credentials.

This verifies synthesis/content, not self-hosted GPU performance or model pinning.
The demo UI revision is pinned in the report; backend weights are not exposed.
"""
import asyncio
import hashlib
import io
import json
import time
from pathlib import Path
import httpx
import soundfile as sf

BASE="https://openbmb-voxcpm-demo.hf.space"
CASES=[
    ("ar_basic","تم استلام طلبك. يرجى الاحتفاظ برقم الطلب."),
    ("ar_digits","رقم الطلب 1047. الموعد في 15 أكتوبر."),
    ("ar_spoken_digits","رقم الطلب هو واحد صفر أربعة سبعة. موعدك يوم الخامس عشر من أكتوبر."),
    ("ar_mixed","يمكنك متابعة الطلب باستخدام رقم Reference ID في الموقع."),
    ("ar_handoff","سأحولك الآن إلى موظف خدمة العملاء. يرجى الانتظار."),
    ("en_basic","Your request has been received. Please keep the reference number.")]


async def synthesize(client,text):
    r=await client.post(BASE+"/gradio_api/call/generate",json={"data":[text,"A clear neutral adult Arabic customer service voice.",None,False,"",2.0,False,False]})
    r.raise_for_status();event_id=r.json()["event_id"]
    complete=None;kind=None
    async with client.stream("GET",BASE+"/gradio_api/call/generate/"+event_id) as stream:
        stream.raise_for_status()
        async for line in stream.aiter_lines():
            if line.startswith("event: "):kind=line[7:]
            if line.startswith("data: ") and kind in {"complete","error"}:
                value=json.loads(line[6:])
                if kind=='error':raise RuntimeError("official demo synthesis failure")
                complete=value;break
    if not complete:raise RuntimeError("no completed generation")
    item=complete[0];url=item.get("url")
    if not url:url=BASE+"/gradio_api/file="+item['path']
    if not url.startswith(BASE+"/"):raise ValueError("unexpected output host")
    r=await client.get(url);r.raise_for_status()
    return r.content


async def main():
    root=Path('artifacts/raw');root.mkdir(parents=True,exist_ok=True)
    results=[]
    async with httpx.AsyncClient(timeout=httpx.Timeout(150,connect=10)) as c:
        for cid,text in CASES:
            start=time.perf_counter();item={'model':'VoxCPM2 official Nano-vLLM demo','case':cid,'input':text,'backend_revision':'not_exposed','demo_revision':'5b015bfaa16e8a6a35bb1eefb093787c7e3f0352'}
            try:
                data=await synthesize(c,text);audio,sr=sf.read(io.BytesIO(data),always_2d=True)
                path=root/('voxcpm2-'+cid+'.mp3');path.write_bytes(data)
                item.update(status='success',path=str(path),duration=len(audio)/sr,sample_rate=sr,sha256=hashlib.sha256(data).hexdigest())
            except Exception as e:item.update(status='failed',error=type(e).__name__)
            item['elapsed_seconds']=time.perf_counter()-start
            if item.get('duration'):item['rtf_full_response']=item['elapsed_seconds']/item['duration']
            results.append(item);(root/'voxcpm2.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
            print(cid,item['status'],item.get('duration'),item['elapsed_seconds'],flush=True)

if __name__=='__main__':asyncio.run(main())
