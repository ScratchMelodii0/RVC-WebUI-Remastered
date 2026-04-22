import os
import re
import wave
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple

import numpy as np


@dataclass
class TTSRequest:
    text: str
    backend: str
    speed: float = 1.0
    pitch_shift: float = 0.0
    style_prompt: str = ""
    emotion: str = "neutral"
    pause_seconds: float = 0.15
    use_ssml: bool = False


class TTSPipeline:
    """Pipeline de TTS con arquitectura de backends intercambiables.

    Implementa un backend local placeholder y deja preparada la estructura
    para integrar motores reales (Fish Speech, CosyVoice2, XTTS-v2, etc.).
    """

    BACKENDS: Dict[str, str] = {
        "edge_tts_fallback": "Edge-TTS fallback (CPU)",
        "fish_speech": "Fish Speech",
        "cosyvoice2": "CosyVoice2",
        "xtts_v2": "XTTS-v2",
        "styletts2": "StyleTTS2",
        "kokoro": "Kokoro",
        "melo_tts": "MeloTTS",
    }

    def __init__(self, output_root: str = "assets/tts_models"):
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)

    def available_backends(self):
        return list(self.BACKENDS.keys())

    def synthesize(self, request: TTSRequest) -> Tuple[str, str]:
        clean_text = (request.text or "").strip()
        if not clean_text:
            return "❌ Texto vacío. Escribe un prompt de TTS.", ""

        # TODO: reemplazar por inferencia real del backend seleccionado.
        output_path = self._placeholder_wave(clean_text, request)
        status = (
            f"✅ TTS generado con backend '{request.backend}' "
            f"({self.BACKENDS.get(request.backend, 'custom')})."
        )
        return status, str(output_path)

    def tts_to_rvc(self, request: TTSRequest, rvc_model_name: str) -> Tuple[str, str]:
        status, audio_path = self.synthesize(request)
        if not audio_path:
            return status, ""

        model_msg = rvc_model_name if rvc_model_name else "(sin modelo RVC seleccionado)"
        # TODO: encadenar llamada real vc.vc_single/vc pipeline.
        msg = (
            f"{status}\n"
            f"🧪 Pipeline TTS→RVC preparado. Modelo objetivo: {model_msg}. "
            "(Actualmente en modo scaffold para integración incremental)."
        )
        return msg, audio_path

    def _placeholder_wave(self, text: str, request: TTSRequest) -> Path:
        sample_rate = 24000
        words = max(1, len(re.findall(r"\S+", text)))
        dur_s = min(18.0, max(1.5, words * 0.28 / max(request.speed, 0.6)))
        t = np.linspace(0, dur_s, int(sample_rate * dur_s), endpoint=False)

        base_freq = 175.0 + (request.pitch_shift * 8.0)
        style_boost = 1.0 + min(len(request.style_prompt), 40) / 200.0
        waveform = (
            0.18 * np.sin(2 * np.pi * base_freq * t)
            + 0.08 * np.sin(2 * np.pi * base_freq * 2.0 * t)
            + 0.04 * np.sin(2 * np.pi * base_freq * 3.2 * t)
        )
        waveform *= style_boost
        waveform = np.clip(waveform, -0.95, 0.95)
        pcm = (waveform * 32767).astype(np.int16)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        out_path = self.output_root / f"tts_preview_{timestamp}.wav"
        with wave.open(str(out_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm.tobytes())
        return out_path
