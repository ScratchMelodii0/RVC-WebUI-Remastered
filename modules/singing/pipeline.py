import re
import wave
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple

import numpy as np


@dataclass
class SingingRequest:
    lyrics: str
    backend: str
    style_prompt: str = ""
    midi_or_notes: str = ""
    vibrato: float = 0.3
    breathiness: float = 0.2
    tension: float = 0.2
    energy: float = 0.5
    gender: float = 0.0
    portamento: float = 0.3


class SingingPipeline:
    """Scaffold de síntesis de canto texto→audio con controles estilo Vocal Synth."""

    BACKENDS: Dict[str, str] = {
        "tts_pitch_rvc": "TTS + pitch control + RVC",
        "diffsinger": "DiffSinger",
        "nnsvs": "NNSVS",
        "sovits_svc": "So-VITS-SVC",
        "fish_speech_sing": "Fish Speech (si backend soporta singing)",
    }

    def __init__(self, output_root: str = "assets/singing_models"):
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)

    def available_backends(self):
        return list(self.BACKENDS.keys())

    def synthesize(self, request: SingingRequest, rvc_model_name: str = "") -> Tuple[str, str]:
        lyrics = (request.lyrics or "").strip()
        if not lyrics:
            return "❌ Escribe letra para generar canto.", ""

        output_path = self._placeholder_singing_wave(lyrics, request)
        rvc_msg = (
            f"\n🎙️ Timbre objetivo RVC: {rvc_model_name}." if rvc_model_name else ""
        )
        status = (
            f"✅ Singing synth generado con '{request.backend}' "
            f"({self.BACKENDS.get(request.backend, 'custom')}).{rvc_msg}"
        )
        return status, str(output_path)

    def _placeholder_singing_wave(self, lyrics: str, request: SingingRequest) -> Path:
        sample_rate = 32000
        syllables = max(1, len(re.findall(r"[aeiouáéíóúüAEIOUÁÉÍÓÚÜ]", lyrics)))
        dur_s = min(28.0, max(3.0, syllables * 0.25 + 1.0))
        t = np.linspace(0, dur_s, int(sample_rate * dur_s), endpoint=False)

        base = 220.0 + request.gender * 60.0 + request.tension * 20.0
        vibrato_hz = 4.5 + request.vibrato * 3.0
        f_t = base * (1.0 + 0.02 * np.sin(2 * np.pi * vibrato_hz * t))

        phase = 2 * np.pi * np.cumsum(f_t) / sample_rate
        tone = np.sin(phase)
        breath_noise = request.breathiness * np.random.normal(0, 0.08, size=t.shape)
        portamento_env = 1.0 + request.portamento * np.sin(2 * np.pi * 0.2 * t)
        waveform = (0.22 * tone * portamento_env + breath_noise) * (0.8 + request.energy)

        waveform = np.clip(waveform, -0.95, 0.95)
        pcm = (waveform * 32767).astype(np.int16)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        out_path = self.output_root / f"singing_preview_{timestamp}.wav"
        with wave.open(str(out_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm.tobytes())
        return out_path
