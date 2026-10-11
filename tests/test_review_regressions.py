import asyncio
import importlib.util
import json
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx
import pytest
import uvicorn
from speech_gateway.evaluation_budget import Budget
from speech_gateway.metrics import score
from speech_gateway.text import speech_chunks, prepare_speech
from test_core import FakeProviders, session
ROOT=Path(__file__).resolve().parents[1]


def script(name):
    spec=importlib.util.spec_from_file_location(name, ROOT/'scripts'/(name+'.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_readme_env_file_launch(tmp_path, monkeypatch):
    p=tmp_path/'.env';p.write_text('DH_TEST_ENV_LOADED=ok\n')
    monkeypatch.delenv('DH_TEST_ENV_LOADED',raising=False)
    uvicorn.Config('speech_gateway.server:create_app',factory=True,env_file=p)
    import os
    assert os.environ['DH_TEST_ENV_LOADED']=='ok'
    monkeypatch.delenv('DH_TEST_ENV_LOADED')


@pytest.mark.parametrize('error',[httpx.ReadTimeout('offline'),asyncio.CancelledError()])
async def test_paid_continuation_failure_keeps_reservation(tmp_path, monkeypatch,error):
    monkeypatch.syspath_prepend(str(ROOT/'scripts'));m=script('evaluate_tts_content')
    monkeypatch.chdir(tmp_path);root=Path('artifacts/raw');root.mkdir(parents=True)
    Budget(root/'cost.json').reserve(4.9,'prior_unknown')
    monkeypatch.setattr(m.getpass,'getpass',lambda _: 'offline-test-value')
    class OfflineClient:
        def __init__(self,**kw):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,*args,**kw):raise error
    monkeypatch.setattr(m.httpx,'AsyncClient',OfflineClient)
    with pytest.raises(type(error)):await m.main()
    restarted=Budget(root/'cost.json')
    assert restarted.snapshot()['committed']==pytest.approx(5)
    assert restarted.snapshot()['unknown']==2
    with pytest.raises(RuntimeError):restarted.reserve(.01,'retry')


def test_budget_concurrent_views_and_settlement(tmp_path):
    path=tmp_path/'cost.json'
    def reserve(_):
        try:return Budget(path,cap=1).reserve(.1,'offline')
        except RuntimeError:return None
    with ThreadPoolExecutor(8) as pool:ids=[x for x in pool.map(reserve,range(20)) if x]
    assert len(set(ids))==10
    b=Budget(path,cap=1);b.settle(ids[0],{'cost':.01})
    assert b.snapshot()['committed']==pytest.approx(.91) and b.snapshot()['actual']==.01
    with pytest.raises(ValueError):b.settle(ids[0],{'cost':0})
    path.write_text('{truncated')
    with pytest.raises(ValueError):Budget(path,cap=1)
    assert path.read_text()=='{truncated'


async def test_stale_business_result_never_calls_tts():
    entered=asyncio.Event()
    class LateBusiness(FakeProviders):
        def __init__(self):super().__init__();self.tts_calls=[]
        async def business(self,sid,text):
            entered.set()
            try:await asyncio.sleep(60)
            except asyncio.CancelledError:pass
            return {'reply':'late reply','handoff':False}
        async def tts(self,text):self.tts_calls.append(text);return b'\0\0'*320
    p=LateBusiness();s,e,a,j=await session(p)
    await s.submit(b'\0\0'*320);old=s.task;await entered.wait();await s.interrupt();await old
    assert p.tts_calls==[] and a==[] and s.semaphore._value==1
    await s.close();j.close()


async def test_stale_tts_result_stops_before_next_sentence():
    entered=asyncio.Event()
    class LateTTS(FakeProviders):
        def __init__(self):super().__init__();self.calls=[]
        async def business(self,sid,text):return {'reply':'first. second.','handoff':False}
        async def tts(self,text):
            self.calls.append(text);entered.set()
            try:await asyncio.sleep(60)
            except asyncio.CancelledError:pass
            return b''
    p=LateTTS();s,e,a,j=await session(p)
    await s.submit(b'\0\0'*320);old=s.task;await entered.wait();await s.interrupt();await old
    assert p.calls==['first.'] and not a and s.semaphore._value==1
    await s.close();j.close()


def test_spoken_id_atomic_boundaries_and_multiple_slots():
    reply='يرجى '*33+'1047.';slots=[{'kind':'id','value':'1047'}]
    out=speech_chunks(reply,slots);spoken='واحد صفر أربعة سبعة'
    assert any(spoken in part for part in out) and all(len(part)<=180 for part in out)
    assert ' '.join(out)==prepare_speech(reply,slots).strip()
    out=speech_chunks('x '*80+'1047 ثم 22.',slots+[{'kind':'id','value':'22'}])
    assert any(spoken in part for part in out) and any('اثنان اثنان' in part for part in out)
    assert speech_chunks('9'*30,[{'kind':'id','value':'9'*30}])==[' '.join(['تسعة']*30)]
    with pytest.raises(ValueError):speech_chunks('8'*30,[{'kind':'id','value':'8'*30}])


@pytest.mark.parametrize('statuses',[[503],[200,503],[]])
def test_report_failure_and_missing_optional_results(tmp_path,statuses):
    raw=tmp_path/'raw';raw.mkdir();rows=[]
    for status in statuses:
        row={'model':'offline','condition':'clean','status':status,'elapsed_seconds':1}
        if status==200:row['scores']=score('word','word')
        rows.append(row)
    (raw/'asr.json').write_text(json.dumps(rows))
    out=tmp_path/'out';result=script('build_report').generate(raw,out,tmp_path/'missing-manifest')
    if statuses:
        r=result['asr'][0]
        assert r['successful']==statuses.count(200) and r['failed']==statuses.count(503)
        if 200 not in statuses:assert r['latency_seconds']['p50'] is None and r['wer']['rate'] is None
    text=(out/'test-report.md').read_text()
    assert '未执行' in text and '120次成功' not in text and '六条' not in text
    assert result['budget'] is None and not result['availability']['voxcpm2']
    assert result['gateway_deployment'] is None and 'CPU Gateway：未执行' in text


def test_browser_old_callbacks_do_not_end_new_connection():
    node=shutil.which('node')
    if not node:pytest.skip('Node required for client regression')
    subprocess.run([node,str(ROOT/'tests/test_client.cjs')],check=True,capture_output=True,text=True)
