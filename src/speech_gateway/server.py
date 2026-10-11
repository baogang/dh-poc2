import asyncio
import json
import secrets
import time
from contextlib import asynccontextmanager
from importlib.resources import files
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import FileResponse
from .config import Settings
from .providers import HTTPProviders
from .runtime import Admission, Session
from .journal import Journal
from .genesys import GenesysProtocol
from .vad import TurnVAD


def create_app(settings=None, providers=None, vad_factory=TurnVAD):
    s = settings or Settings.env()
    p = providers or HTTPProviders(s)
    journal, admission = Journal(s.journal_path), Admission(s.max_sessions)
    jobs = asyncio.Semaphore(s.max_jobs)

    @asynccontextmanager
    async def lifespan(app):
        yield
        journal.close()
        if hasattr(p, "close"):
            await p.close()

    app = FastAPI(lifespan=lifespan)
    app.state.admission, app.state.journal = admission, journal

    @app.get("/")
    async def index():
        return FileResponse(str(files("speech_gateway").joinpath("web/index.html")))

    @app.get("/worklet.js")
    async def worklet():
        return FileResponse(str(files("speech_gateway").joinpath("web/worklet.js")), media_type="text/javascript")

    @app.get("/health")
    async def health():
        return {"status": "ok", "mode": "demo_business" if s.demo_business else "external_business"}

    @app.get("/metrics")
    async def metrics(request: Request):
        if not secrets.compare_digest(request.headers.get("authorization", ""), "Bearer "+s.gateway_token):
            raise HTTPException(401)
        return {"sessions": len(admission.active), "limit": admission.maximum, "events": journal.counts}

    async def connect(ws, genesys=False):
        if genesys:
            # PoC bearer gate. Production must terminate Genesys HMAC verification at an ingress.
            if not secrets.compare_digest(ws.headers.get("authorization", ""), "Bearer "+s.genesys_token):
                await ws.close(code=1008)
                return
        elif ws.headers.get("origin") not in s.origins:
            await ws.close(code=1008)
            return
        await ws.accept()
        if not genesys:
            try:
                async with asyncio.timeout(5):
                    auth = await ws.receive_json()
                if not isinstance(auth, dict) or auth.get("type") != "auth" or not isinstance(auth.get("token"), str) or not secrets.compare_digest(auth["token"], s.gateway_token):
                    await ws.close(code=1008)
                    return
            except (ValueError, TimeoutError, WebSocketDisconnect):
                await ws.close(code=1008)
                return
        sid = admission.acquire()
        if sid is None:
            await ws.send_json({"type": "error", "reason": "capacity"})
            await ws.close(code=1013)
            return
        proto = GenesysProtocol() if genesys else None
        vad, session = None, None
        try:
            vad = vad_factory()

            async def event(data):
                if proto:
                    if proto.opened:
                        mapped = proto.event(data)
                        if mapped:
                            await ws.send_json(mapped)
                else:
                    await ws.send_json(data)

            async def audio(data, epoch):
                if proto:
                    await ws.send_bytes(proto.codec.encode(data))
                else:
                    await ws.send_json({"type": "audio", "epoch": epoch, "sample_rate": 16000})
                    await ws.send_bytes(data)

            session = Session(sid, p, event, audio, journal, jobs)
            if not proto:
                await event({"type": "ready", "session_id": sid, "epoch": 0})
            window, count = time.monotonic(), 0
            async with asyncio.timeout(600):
                while True:
                    async with asyncio.timeout(45):
                        msg = await ws.receive()
                    if msg["type"] == "websocket.disconnect":
                        break
                    now = time.monotonic()
                    if now-window >= 1:
                        window, count = now, 0
                    count += 1
                    if count > 100:
                        raise ValueError("frame rate exceeded")
                    if msg.get("bytes") is not None:
                        data = msg["bytes"]
                        if not data or len(data) > (8000 if proto else 32000) or (not proto and len(data)%2):
                            raise ValueError("invalid audio frame")
                        if proto:
                            if not proto.opened:
                                raise ValueError("Genesys open required")
                            data = proto.codec.decode(data)
                        if session.transferred:
                            continue
                        start, turn = await vad.feed(data)
                        if start:
                            await session.interrupt()
                        if turn:
                            await session.submit(turn)
                    elif msg.get("text") is not None:
                        if len(msg["text"]) > 16384:
                            raise ValueError("control frame too large")
                        data = json.loads(msg["text"])
                        if not isinstance(data, dict):
                            raise ValueError("control must be an object")
                        if proto:
                            response = proto.receive(data)
                            if response:
                                await ws.send_json(response)
                            if data["type"] == "close":
                                break
                            if data["type"] == "dtmf" and data.get("parameters", {}).get("digit") == "0":
                                await session.handoff("dtmf")
                        elif data.get("type") == "stop":
                            await session.interrupt()
                        elif data.get("type") == "handoff":
                            await session.handoff("user_requested")
                        elif data.get("type") == "commit":
                            turn = vad.manual()
                            if turn:
                                await session.submit(turn)
                            else:
                                await event({"type": "clarify", "reason": "no_audio"})
                        elif data.get("type") == "playback_done":
                            journal.record(sid, "playback_done", session.epoch)
                        elif data.get("type") == "ping":
                            await event({"type": "pong"})
                        else:
                            raise ValueError("unsupported control")
        except WebSocketDisconnect:
            pass
        except (ValueError, KeyError, TypeError, TimeoutError):
            await ws.close(code=1008)
        finally:
            if session:
                await session.close()
            if vad:
                vad.close()
            admission.release(sid)

    @app.websocket("/ws/website")
    async def website(ws: WebSocket):
        await connect(ws)

    @app.websocket("/ws/genesys")
    async def genesys(ws: WebSocket):
        await connect(ws, True)

    return app
