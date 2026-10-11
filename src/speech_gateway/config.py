from dataclasses import dataclass
import os


@dataclass
class Settings:
    gateway_token: str
    genesys_token: str
    origins: tuple[str, ...] = ("http://localhost:8080", "http://127.0.0.1:8080")
    max_sessions: int = 20
    max_jobs: int = 4
    asr_url: str = "http://asr:8000/v1"
    tts_url: str = "http://tts:8000/v1"
    api_key: str = ""
    asr_model: str = "Qwen/Qwen3-ASR-1.7B"
    tts_model: str = "openbmb/VoxCPM2"
    voice: str = "default"
    business_url: str = ""
    business_token: str = ""
    demo_business: bool = True
    journal_path: str = "runtime/events.sqlite"

    def __post_init__(self):
        if min(len(self.gateway_token), len(self.genesys_token)) < 32:
            raise ValueError("configure independent gateway/Genesys secrets of at least 32 characters")
        if self.max_sessions < 1 or self.max_jobs < 1:
            raise ValueError("positive admission limits required")
        if not self.demo_business and not self.business_url:
            raise ValueError("BUSINESS_URL required when demo business is disabled")

    @classmethod
    def env(cls):
        return cls(gateway_token=os.getenv("GATEWAY_TOKEN", ""), genesys_token=os.getenv("GENESYS_TOKEN", ""),
            origins=tuple(os.getenv("ALLOWED_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080").split(",")),
            max_sessions=int(os.getenv("MAX_SESSIONS", "20")), max_jobs=int(os.getenv("MAX_MODEL_JOBS", "4")),
            asr_url=os.getenv("ASR_BASE_URL", "http://asr:8000/v1"), tts_url=os.getenv("TTS_BASE_URL", "http://tts:8000/v1"),
            api_key=os.getenv("MODEL_API_KEY", ""), asr_model=os.getenv("ASR_MODEL", "Qwen/Qwen3-ASR-1.7B"),
            tts_model=os.getenv("TTS_MODEL", "openbmb/VoxCPM2"), voice=os.getenv("TTS_VOICE", "default"),
            business_url=os.getenv("BUSINESS_URL", ""), business_token=os.getenv("BUSINESS_TOKEN", ""),
            demo_business=os.getenv("DEMO_BUSINESS", "true").lower()=="true", journal_path=os.getenv("JOURNAL_PATH", "runtime/events.sqlite"))
