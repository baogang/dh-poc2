"""Download three bounded SADA test files and extract deterministic strata.

Local-only CC BY-NC-SA 4.0 evaluation assets; never commit audio or transcripts.
"""
import csv
import hashlib
import io
import json
import urllib.request
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from speech_gateway.codec import wav_bytes, telephone_wav

REV = "f45d9ad8e60aa3613229322e0712eb5874ff94f6"
BASE = f"https://huggingface.co/datasets/khaledalganem/sada2022/resolve/{REV}/"


def fetch(path, dest, maximum=25_000_000):
    if not dest.exists():
        with urllib.request.urlopen(BASE+path, timeout=60) as r:
            data = r.read(maximum+1)
        if len(data)>maximum:
            raise ValueError("download size exceeded")
        dest.write_bytes(data)


def main():
    root = Path("data/sada")
    root.mkdir(parents=True, exist_ok=True)
    fetch("test.csv", root/"test.csv", 4_000_000)
    rows = list(csv.DictReader((root/"test.csv").open()))
    selected=[]
    for dialect in ["Najdi", "Hijazi", "Khaliji", "ModernStandardArabic"]:
        eligible=[r for r in rows if r["SpeakerDialect"]==dialect and 3<float(r["SegmentLength"])<12
                  and r["Environment"]=="Clean -- نظيف" and len(r["GroundTruthText"].split())>=6]
        source=eligible[0]["FileName"]
        selected.extend([r for r in eligible if r["FileName"]==source][:6])
    decoded={}
    manifest=[]
    for r in selected:
        source=r["FileName"]
        if source not in decoded:
            dest=root/Path(source).name
            fetch(source,dest)
            decoded[source]=sf.read(dest,dtype="float32",always_2d=True)
        audio,rate=decoded[source]
        clip=audio[int(float(r["SegmentStart"])*rate):int(float(r["SegmentEnd"])*rate)].mean(axis=1)
        from math import gcd
        g=gcd(rate,16000)
        if rate!=16000:clip=resample_poly(clip,16000//g,rate//g)
        pcm=(np.clip(clip,-1,1)*32767).astype("<i2").tobytes()
        item={"id":r["SegmentID"],"source":source,"split":"test","dialect":r["SpeakerDialect"],
              "speaker":r["Speaker"],"show":r["ShowName"],"reference":r["GroundTruthText"],
              "start":float(r["SegmentStart"]),"end":float(r["SegmentEnd"]),"duration":len(pcm)/32000,
              "audio":{},"sha256":{}}
        for condition,data in [("clean",wav_bytes(pcm)),("pcmu",telephone_wav(pcm))]:
            path=root/(r["SegmentID"]+"-"+condition+".wav");path.write_bytes(data)
            item["audio"][condition]=str(path);item["sha256"][condition]=hashlib.sha256(data).hexdigest()
        manifest.append(item)
    (root/"manifest.json").write_text(json.dumps({"source":BASE,"revision":REV,"license":"CC-BY-NC-SA-4.0",
        "selection":"first eligible source per dialect, first six clean 3..12s utterances with >=6 words; before inference",
        "samples":manifest},ensure_ascii=False,indent=2))
    print(json.dumps({"samples":len(manifest),"sources":len(decoded),"seconds":sum(x["duration"] for x in manifest)}))

if __name__=="__main__":main()
