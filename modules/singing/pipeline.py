import re
import wave
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

try:
    import mido  # type: ignore
except Exception:  # pragma: no cover - optional dependency fallback
    mido = None

from typing import Dict, Tuple

import numpy as np


@dataclass
class SingingRequest:
    lyrics: str
    backend: str
    style_prompt: str = ""
    midi_or_notes: str = ""
    midi_path: str = ""
    phoneme_language: str = "auto"
    phoneme_text: str = ""
    vibrato: float = 0.3
    breathiness: float = 0.2
    tension: float = 0.2
    energy: float = 0.5
    gender: float = 0.0
    portamento: float = 0.3
    tempo_bpm: int = 120


class SingingPipeline:
    """SynthRVC scaffold para síntesis vocal tipo Vocaloid/UTAU + RVC."""

    BACKENDS: Dict[str, str] = {
        "synthrvc_hybrid": "SynthRVC Hybrid (TTS + pitch + RVC)",


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

    def synthesize(
        self,
        request: SingingRequest,
        rvc_model_name: str = "",
    ) -> Tuple[str, str, str]:
        lyrics = (request.lyrics or "").strip()
        if not lyrics:
            return "❌ Escribe letra para generar canto.", "", ""

        notes, note_source = self._resolve_note_events(request)
        if not notes:
            return (
                "❌ No se pudieron interpretar notas. Usa un MIDI o el formato C4:0.5 D4:1.0",
                "",
                "",
            )

        phoneme_preview = self._resolve_phonemes(request, lyrics)
        output_path = self._render_singing_wave(notes, request)

    def synthesize(self, request: SingingRequest, rvc_model_name: str = "") -> Tuple[str, str]:
        lyrics = (request.lyrics or "").strip()
        if not lyrics:
            return "❌ Escribe letra para generar canto.", ""

        output_path = self._placeholder_singing_wave(lyrics, request)
        rvc_msg = (
            f"\n🎙️ Timbre objetivo RVC: {rvc_model_name}." if rvc_model_name else ""
        )
        status = (
            f"✅ SynthRVC generado con '{request.backend}' "
            f"({self.BACKENDS.get(request.backend, 'custom')})."
            f"\n🎼 Fuente de notas: {note_source}.{rvc_msg}"
        )
        debug = (
            f"Phoneme lang: {request.phoneme_language}\n"
            f"Phoneme preview: {phoneme_preview[:180]}\n"
            f"Notes parsed: {len(notes)} (first: {notes[:5]})"
        )
        if request.midi_path and not mido:
            debug += "\n⚠️ MIDI parser not available: install `mido` to parse uploaded MIDI files."
        return status, str(output_path), debug

    def _resolve_note_events(self, request: SingingRequest) -> Tuple[List[Tuple[float, float]], str]:
        if request.midi_path:
            midi_notes = self._parse_midi_file(request.midi_path)
            if midi_notes:
                return midi_notes, f"MIDI file ({Path(request.midi_path).name})"

        text_notes = self._parse_text_notes(request.midi_or_notes)
        if text_notes:
            return text_notes, "text notes"

        return self._default_scale(), "default scale"

    def _parse_midi_file(self, midi_path: str) -> List[Tuple[float, float]]:
        if not mido:
            return []

        try:
            mid = mido.MidiFile(midi_path)
            ticks_per_beat = max(1, mid.ticks_per_beat)
            tempo = 500000  # default 120 bpm in microseconds per beat
            notes: List[Tuple[float, float]] = []
            active = {}
            for track in mid.tracks:
                abs_ticks = 0
                for msg in track:
                    abs_ticks += msg.time
                    if msg.type == "set_tempo":
                        tempo = msg.tempo
                    elif msg.type == "note_on" and msg.velocity > 0:
                        active[msg.note] = abs_ticks
                    elif msg.type in {"note_off", "note_on"} and msg.note in active:
                        start = active.pop(msg.note)
                        dur_ticks = max(1, abs_ticks - start)
                        duration = (dur_ticks / ticks_per_beat) * (tempo / 1_000_000)
                        freq = self._midi_to_freq(msg.note)
                        notes.append((freq, min(2.5, max(0.08, duration))))
            return notes[:800]
        except Exception:
            return []

    def _parse_text_notes(self, note_text: str) -> List[Tuple[float, float]]:
        if not note_text:
            return []

        pattern = re.compile(r"([A-Ga-g][#b]?\d)\s*[:=]\s*([0-9]*\.?[0-9]+)")
        matches = pattern.findall(note_text)
        note_events: List[Tuple[float, float]] = []
        for note_name, duration in matches:
            freq = self._note_to_freq(note_name)
            if freq <= 0:
                continue
            note_events.append((freq, min(2.5, max(0.08, float(duration)))))
        return note_events[:800]

    def _resolve_phonemes(self, request: SingingRequest, lyrics: str) -> str:
        if request.phoneme_text.strip():
            return request.phoneme_text.strip()

        lang = request.phoneme_language
        if lang == "ja":
            return self._simple_japanese_phoneme_map(lyrics)
        if lang == "es":
            return self._simple_spanish_phoneme_map(lyrics)
        if lang == "en":
            return self._simple_english_phoneme_map(lyrics)
        return lyrics

    def _render_singing_wave(
        self,
        notes: List[Tuple[float, float]],
        request: SingingRequest,
    ) -> Path:
        sample_rate = 32000
        audio_chunks = []
        vibrato_hz = 4.5 + request.vibrato * 3.5
        rng = np.random.default_rng(114514)

        for idx, (base_freq, dur_s) in enumerate(notes):
            dur_s = max(0.06, dur_s)
            t = np.linspace(0, dur_s, int(sample_rate * dur_s), endpoint=False)

            pitch_shape = 1.0 + 0.022 * np.sin(2 * np.pi * vibrato_hz * t)
            portamento_target = 1.0 + request.portamento * 0.03 * np.sin(2 * np.pi * 0.6 * t)
            freq_t = base_freq * pitch_shape * portamento_target

            phase = 2 * np.pi * np.cumsum(freq_t) / sample_rate
            harmonic = np.sin(phase) + 0.35 * np.sin(2 * phase) + 0.15 * np.sin(3 * phase)

            breath_noise = request.breathiness * rng.normal(0, 0.05, size=t.shape)
            envelope = np.minimum(1.0, t / 0.02) * np.minimum(1.0, (dur_s - t + 1e-4) / 0.03)
            energy_gain = 0.35 + request.energy * 0.9
            tension_gain = 1.0 + request.tension * 0.3
            gender_shift = 1.0 + request.gender * 0.1

            chunk = (0.22 * harmonic * energy_gain * tension_gain * gender_shift + breath_noise) * envelope
            # micro-rest para separar sílabas
            if idx < len(notes) - 1:
                pause = np.zeros(int(sample_rate * 0.012), dtype=np.float64)
                chunk = np.concatenate([chunk, pause])
            audio_chunks.append(chunk)

        waveform = np.concatenate(audio_chunks) if audio_chunks else np.zeros(sample_rate)
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
        out_path = self.output_root / f"synthrvc_preview_{timestamp}.wav"
        out_path = self.output_root / f"singing_preview_{timestamp}.wav"
        with wave.open(str(out_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm.tobytes())
        return out_path

    @staticmethod
    def _default_scale() -> List[Tuple[float, float]]:
        return [
            (261.63, 0.4),
            (293.66, 0.4),
            (329.63, 0.4),
            (349.23, 0.5),
            (392.00, 0.6),
            (440.00, 0.8),
        ]

    @staticmethod
    def _note_to_freq(note_name: str) -> float:
        note_name = note_name.strip().upper()
        pattern = re.match(r"^([A-G])([#B]?)(\d)$", note_name)
        if not pattern:
            return 0.0
        note, accidental, octave_str = pattern.groups()
        semitone_map = {
            "C": 0,
            "D": 2,
            "E": 4,
            "F": 5,
            "G": 7,
            "A": 9,
            "B": 11,
        }
        semitone = semitone_map[note]
        if accidental == "#":
            semitone += 1
        elif accidental == "B":
            semitone -= 1
        octave = int(octave_str)
        midi_note = (octave + 1) * 12 + semitone
        return SingingPipeline._midi_to_freq(midi_note)

    @staticmethod
    def _midi_to_freq(midi_note: int) -> float:
        return 440.0 * (2 ** ((midi_note - 69) / 12.0))

    @staticmethod
    def _simple_japanese_phoneme_map(text: str) -> str:
        # Conversión super-ligera para scaffold (Hiragana/Katakana se dejan intactas)
        text = text.lower().replace("shi", "し").replace("tsu", "つ").replace("chi", "ち")
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _simple_spanish_phoneme_map(text: str) -> str:
        text = text.lower()
        text = text.replace("ll", "y").replace("ch", "tʃ").replace("rr", "r:")
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _simple_english_phoneme_map(text: str) -> str:
        text = text.lower()
        text = text.replace("th", "ð").replace("sh", "ʃ").replace("ch", "tʃ")
        return re.sub(r"\s+", " ", text).strip()
