"""Real inference only. Hidden credential input; no account reads or secret writes.

Authorisation: <=USD5 total; fixed SADA test clips + authored TTS sentences.
Failed/unknown usage reserves a conservative per-call amount. Outputs local-only.
"""
import asyncio
import argparse
import base64
import getpass
import hashlib
import io
import json
import time
from pathlib import Path
import httpx
import soundfile as sf
from speech_gateway.metrics import score
from speech_gateway.evaluation_budget import Budget

MODELS=["qwen/qwen3-asr-1.7b", "qwen/qwen3-asr-0.6b", "nvidia/nemotron-3.5-asr-streaming-multilingual-0.6b"]
TTS_CASES=[
    ("en_basic", "Your request has been received. Please keep the reference number."),
    ("en_number", "Your reference number is 1047. Your appointment is on October 15."),
    ("ar_basic", "تم استلام طلبك. يرجى الاحتفاظ برقم الطلب."),
    ("ar_number", "رقم الطلب هو واحد صفر أربعة سبعة. موعدك يوم الخامس عشر من أكتوبر."),
    ("ar_mixed", "يمكنك متابعة الطلب باستخدام رقم Reference ID في الموقع.")]


async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run-dir',default='artifacts/raw')
    parser.add_argument('--ledger', default='artifacts/raw/cost.json')
    args=parser.parse_args();root=Path(args.run_dir)
    if (root/'asr.json').exists() or (root/'tts.json').exists():
        raise RuntimeError('Existing results: use a fresh --run-dir, keep the SAME cumulative ledger')
    key=getpass.getpass("OpenRouter temporary key (hidden): ")
    manifest=json.loads(Path("data/sada/manifest.json").read_text())
    root.mkdir(parents=True,exist_ok=True)
    budget=Budget(args.ledger, cap=5)
    headers={"Authorization":"Bearer "+key}
    results=[]
    semaphore=asyncio.Semaphore(3)
    async with httpx.AsyncClient(timeout=httpx.Timeout(60,connect=10)) as client:
        async def transcribe(model,sample,condition):
            async with semaphore:
                path=Path(sample["audio"][condition]);data=path.read_bytes()
                if hashlib.sha256(data).hexdigest()!=sample["sha256"][condition]:raise ValueError("audio hash mismatch")
                call_id=budget.reserve(.02, model)
                start=time.perf_counter()
                item={"id":sample["id"],"model":model,"condition":condition,"dialect":sample["dialect"],"duration":sample["duration"]}
                usage={}
                try:
                    r=await client.post("https://openrouter.ai/api/v1/audio/transcriptions",headers=headers,json={
                        "model":model,"input_audio":{"data":base64.b64encode(data).decode(),"format":"wav"},"language":"ar","temperature":0})
                    item["status"]=r.status_code
                    if r.is_success:
                        body=r.json();usage=body.get("usage",{});text=body.get("text")
                        if not isinstance(text,str):raise ValueError("no transcript")
                        item.update(hypothesis=text,scores=score(sample["reference"],text))
                    else:item["error"]="http_failure"
                except Exception as e:item["error"]=type(e).__name__
                item["elapsed_seconds"]=time.perf_counter()-start
                budget.settle(call_id,usage)
                results.append(item)
                (root/"asr.json").write_text(json.dumps(results,ensure_ascii=False,indent=2))
                print(model.split('/')[1],sample['id'],condition,item.get('status'),item.get('scores',{}).get('wer',{}).get('error_rate'),flush=True)
        # Capability smoke is a real first sample, counted once; failures are recorded, not silently substituted.
        await asyncio.gather(*(transcribe(m,s,c) for s in manifest["samples"] for c in ["clean","pcmu"] for m in MODELS))
        tts=[]
        for model,voice in [("hexgrad/kokoro-82m","af_heart"),("qwen/qwen-audio-3.0-tts-flash","Cherry")]:
            for cid,text in TTS_CASES:
                if model.startswith("hexgrad") and cid.startswith("ar_"):continue
                call_id=budget.reserve(.1, model);start=time.perf_counter();usage={}
                item={"model":model,"case":cid,"input":text,"voice":voice}
                try:
                    r=await client.post("https://openrouter.ai/api/v1/audio/speech",headers=headers,json={"model":model,"input":text,"voice":voice,"response_format":"wav"})
                    item["status"]=r.status_code
                    if r.is_success:
                        a,sr=sf.read(io.BytesIO(r.content),always_2d=True)
                        dest=root/(model.split('/')[1]+"-"+cid+".wav");dest.write_bytes(r.content)
                        item.update(path=str(dest),duration=len(a)/sr,sample_rate=sr,sha256=hashlib.sha256(r.content).hexdigest())
                        # Header cost when available, never query account endpoints.
                        cost=r.headers.get("x-openrouter-cost")
                        if cost:usage={"cost":float(cost)}
                        ref={"id":"tts-"+cid,"duration":len(a)/sr,"audio":{"tts":str(dest)},"sha256":{"tts":item["sha256"]},"reference":text,"dialect":"authored"}
                        await transcribe(MODELS[0],ref,"tts")
                    else:item["error"]="http_failure"
                except Exception as e:item["error"]=type(e).__name__
                item["elapsed_seconds"]=time.perf_counter()-start
                if item.get("duration"):item["rtf_full_response"]=item["elapsed_seconds"]/item["duration"]
                budget.settle(call_id,usage);tts.append(item)
                (root/"tts.json").write_text(json.dumps(tts,ensure_ascii=False,indent=2))
                print("TTS",model,cid,item.get('status'),item.get('error'),flush=True)
    key=""
    print("Budget:", {k:v for k,v in budget.snapshot().items() if k != "calls"})

if __name__=="__main__":asyncio.run(main())
