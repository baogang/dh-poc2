"""M02/M11: bounded Genesys AudioHook v2 protocol adapter, PCMU external only.

This is a protocol PoC. Live Audio Connector entitlement/authentication and
transfer flow need tenant validation; passive AudioHook must not be assumed duplex.
"""
from .codec import PCMUCodec


class GenesysProtocol:
    def __init__(self):
        self.id, self.clientseq, self.seq, self.opened = None, 0, 0, False
        self.codec = PCMUCodec()

    def message(self, kind, parameters=None):
        self.seq += 1
        return {"version": "2", "id": self.id, "type": kind, "seq": self.seq,
                "clientseq": self.clientseq, "parameters": parameters or {}}

    def receive(self, data):
        if data.get("version") != "2" or type(data.get("seq")) is not int or data["seq"] <= self.clientseq:
            raise ValueError("invalid Genesys version/sequence")
        if self.id is not None and data.get("id") != self.id:
            raise ValueError("stream id mismatch")
        self.clientseq = data["seq"]
        kind, p = data.get("type"), data.get("parameters", {})
        if not isinstance(p, dict):
            raise ValueError("invalid control parameters")
        if kind == "open":
            if self.opened or not isinstance(data.get("id"), str):
                raise ValueError("duplicate/invalid open")
            if not isinstance(p.get("media"), list):
                raise ValueError("media list required")
            valid = [m for m in p["media"] if isinstance(m, dict) and m.get("format") == "PCMU" and m.get("rate") == 8000
                     and m.get("channels") == ["external"] and m.get("type") == "audio"]
            if not valid:
                raise ValueError("only PCMU 8kHz external mono is supported")
            self.id, self.opened = data["id"], True
            return self.message("opened", {"startPaused": False, "media": [valid[0]]})
        if not self.opened:
            raise ValueError("open required")
        if kind == "ping":
            return self.message("pong")
        if kind == "close":
            self.opened = False
            return self.message("closed")
        if kind in {"dtmf", "paused", "resumed", "playback_started", "playback_completed"}:
            return None
        raise ValueError("unsupported control event")

    def event(self, event):
        if event["type"] == "stop":
            self.codec.output_state = None
            return self.message("event", {"entities": [{"type": "barge_in", "data": {}}]})
        if event["type"] == "handoff":
            return self.message("disconnect", {"reason": "completed", "outputVariables": {"action": "transfer"}})
        if event["type"] == "error":
            return self.message("disconnect", {"reason": "error", "outputVariables": {"action": "transfer"}})
        return None
