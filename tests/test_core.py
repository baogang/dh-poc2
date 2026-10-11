import asyncio
import io
import json
import numpy as np
import pytest
from fastapi.testclient import TestClient
from speech_gateway.codec import PCMUCodec, wav_bytes
from speech_gateway.config import Settings
from speech_gateway.genesys import GenesysProtocol
from speech_gateway.journal import Journal
from speech_gateway.metrics import score, confusion, capacity, normalize
from speech_gateway.runtime import Admission, Session
from speech_gateway.server import create_app
from speech_gateway.text import chunks, prepare_speech


def settings(**kw):
    return Settings(gateway_token="w"*32, genesys_token="g"*32, journal_path=":memory:", **kw)


def test_metrics_and_preserved_numbers():
    m=score("مرحبا 123 Reference", "مرحبا 124 Reference")
    assert m['wer']['substitutions']==1
    assert m['wer']['error_rate']==pytest.approx(1/3)
    assert normalize("أَهْلاً 123 ID") == "اهلا 123 id"
    assert score("", "noise")['wer']['error_rate'] is None
    assert confusion(8,2,2,8)=={'precision':.8,'recall':.8,'false_positive_rate':.2}


def test_capacity_sensitivity():
    assert capacity()['concurrent_calls']==500
    assert capacity(aht_seconds=180,peak=1)['concurrent_calls']==150
    assert capacity(aht_seconds=600,peak=1)['concurrent_calls']==500


def test_stateful_codec_chunks_equal_whole():
    pcm=(np.sin(np.arange(8000)*.3)*10000).astype('<i2').tobytes()
    a,b=PCMUCodec(),PCMUCodec()
    assert a.encode(pcm)==b''.join(b.encode(pcm[i:i+640]) for i in range(0,len(pcm),640))
    assert wav_bytes(pcm).startswith(b'RIFF')
    with pytest.raises(ValueError):wav_bytes(b'\x00')


def test_text_chunks_protect_ids():
    txt=' '.join(['موعد ABC-1234 1047']*30)
    out=chunks(txt)
    assert all(len(s)<=180 for s in out)
    assert ' '.join(out)==txt
    with pytest.raises(ValueError):chunks('x'*181)
    with pytest.raises(ValueError):chunks(' ')


def test_typed_identifier_pronunciation_and_no_date_guessing():
    reply='رقم الطلب 1047. الموعد 15 أكتوبر.'
    spoken=prepare_speech(reply,[{'kind':'id','value':'1047'}])
    assert spoken=='رقم الطلب واحد صفر أربعة سبعة. الموعد 15 أكتوبر.'
    assert reply=='رقم الطلب 1047. الموعد 15 أكتوبر.'
    with pytest.raises(ValueError):prepare_speech(reply,[{'kind':'id','value':'999'}])
    with pytest.raises(ValueError):prepare_speech(reply,[{'kind':'date','value':'15'}])


def opening(seq=1,fmt='PCMU'):
    return {'version':'2','id':'call-id','seq':seq,'type':'open','parameters':{
        'media':[{'type':'audio','format':fmt,'rate':8000,'channels':['external']}]}}


def test_genesys_open_sequences_and_barge_in():
    p=GenesysProtocol();r=p.receive(opening())
    assert r['type']=='opened' and r['clientseq']==1 and r['seq']==1
    assert p.event({'type':'stop'})['parameters']['entities'][0]['type']=='barge_in'
    assert p.receive({'version':'2','id':'call-id','seq':2,'type':'ping'})['type']=='pong'
    with pytest.raises(ValueError):p.receive({'version':'2','id':'call-id','seq':2,'type':'ping'})
    with pytest.raises(ValueError):GenesysProtocol().receive(opening(fmt='L16'))
    assert p.event({'type':'handoff'})['parameters']['outputVariables']['action']=='transfer'


def test_admission_releases_and_isolates():
    a=Admission(2);s1,s2=a.acquire(),a.acquire()
    assert s1!=s2 and a.acquire() is None
    a.release(s1);a.release(s1)
    assert a.acquire() is not None


class FakeProviders:
    def __init__(self):self.transcript='مرحبا';self.wait=0
    async def asr(self,wav):
        assert wav.startswith(b'RIFF')
        await asyncio.sleep(self.wait)
        return self.transcript
    async def business(self,sid,text):return {'reply':'مرحبا بك.','handoff':text=='موظف'}
    async def tts(self,text):return b'\x00\x00'*320
    async def close(self):pass


async def session(providers=None,sem=None):
    events,audio=[],[]
    async def send(e):events.append(e)
    async def send_audio(a,e):audio.append((a,e))
    j=Journal(':memory:')
    return Session('test',providers or FakeProviders(),send,send_audio,j,sem or asyncio.Semaphore(1)),events,audio,j


async def test_turn_real_flow_contract_and_no_audio_after_interrupt():
    s,events,audio,j=await session()
    await s.submit(b'\x00\x00'*1600);await s.task
    assert [e['type'] for e in events]==['stop','transcript','reply','done']
    assert len(audio)==1
    await s.close();j.close()


async def test_late_provider_return_is_fenced():
    class Stubborn(FakeProviders):
        async def asr(self,wav):
            try:await asyncio.sleep(.05)
            except asyncio.CancelledError:await asyncio.sleep(.01)
            return 'late'
    s,events,audio,j=await session(Stubborn())
    await s.submit(b'\x00\x00'*320);old=s.task
    await asyncio.sleep(.005);await s.interrupt();await old
    assert all(e['type']=='stop' for e in events) and not audio
    await s.close();j.close()


async def test_provider_failure_is_sanitized_and_releases_semaphore():
    class Broken(FakeProviders):
        async def asr(self,wav):raise RuntimeError('secret-key and private URL')
    sem=asyncio.Semaphore(1);s,e,a,j=await session(Broken(),sem)
    await s.submit(b'\x00\x00'*320);await s.task
    assert e[-1]=={'type':'error','reason':'upstream_failure','epoch':1}
    assert sem._value==1 and 'secret-key' not in json.dumps(e)
    await s.close();j.close()


async def test_handoff_does_not_synthesize():
    p=FakeProviders();p.transcript='موظف';s,e,a,j=await session(p)
    await s.submit(b'\x00\x00'*320);await s.task
    assert e[-1]['type']=='handoff' and not a
    count=len(e);await s.submit(b'\x00\x00'*320)
    assert len(e)==count and s.transferred
    await s.close();j.close()


class FakeVAD:
    async def feed(self,a):return False,a
    def close(self):pass


def test_website_auth_origin_and_capacity():
    app=create_app(settings(max_sessions=1),FakeProviders(),FakeVAD)
    with TestClient(app) as c:
        assert c.get('/health').status_code==200
        assert c.get('/metrics').status_code==401
        with pytest.raises(Exception):
            with c.websocket_connect('/ws/website',headers={'origin':'https://evil.example'}):pass
        with c.websocket_connect('/ws/website',headers={'origin':'http://localhost:8080'}) as a:
            a.send_json({'type':'auth','token':'w'*32});assert a.receive_json()['type']=='ready'
            with c.websocket_connect('/ws/website',headers={'origin':'http://localhost:8080'}) as b:
                b.send_json({'type':'auth','token':'w'*32});assert b.receive_json()['reason']=='capacity'
            a.send_bytes(b'\x00\x00'*320)
            assert a.receive_json()['type']=='stop'
            assert a.receive_json()['type']=='transcript'
        assert c.get('/metrics',headers={'authorization':'Bearer '+'w'*32}).json()['sessions']==0


def test_genesys_websocket_protocol_integration():
    app=create_app(settings(),FakeProviders(),FakeVAD)
    with TestClient(app) as c:
        with c.websocket_connect('/ws/genesys',headers={'authorization':'Bearer '+'g'*32}) as ws:
            ws.send_json(opening());assert ws.receive_json()['type']=='opened'
            ws.send_json({'version':'2','id':'call-id','seq':2,'type':'ping'});assert ws.receive_json()['type']=='pong'
            ws.send_json({'version':'2','id':'call-id','seq':3,'type':'dtmf','parameters':{'digit':'0'}})
            assert ws.receive_json()['type']=='event'
            assert ws.receive_json()['parameters']['outputVariables']['action']=='transfer'


def test_private_journal_does_not_store_transcript():
    j=Journal(':memory:');j.record('sid','interrupt',1)
    assert j.db.execute('SELECT session,kind,epoch FROM events').fetchone()==('sid','interrupt',1)
    j.close()


@pytest.mark.parametrize('kw',[{'gateway_token':''},{'max_sessions':0},{'demo_business':False}])
def test_configuration_fails_closed(kw):
    values={'gateway_token':'w'*32,'genesys_token':'g'*32};values.update(kw)
    with pytest.raises(ValueError):Settings(**values)
