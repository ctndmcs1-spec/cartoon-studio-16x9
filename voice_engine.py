"""
Voice Engine - hỗ trợ cả Edge TTS (giọng có sẵn) và VieNeu-TTS (clone giọng).
"""
import io
import os
import re
import asyncio
import edge_tts
import numpy as np
import soundfile as sf

# ============================================================
# EDGE TTS - GIỌNG CÓ SẴN
# ============================================================
async def _edge_synth_async(text: str, voice: str, rate: str, pitch: str,
                            volume: str, want_srt: bool = False):
    """Trả về (audio_bytes, srt_text_or_None)."""
    communicate = edge_tts.Communicate(
        text=text, voice=voice, rate=rate, pitch=pitch, volume=volume
    )
    audio_buf = io.BytesIO()
    boundaries = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_buf.write(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            boundaries.append(chunk)

    srt_text = None
    if want_srt and boundaries:
        srt_text = _boundaries_to_srt(boundaries)

    return audio_buf.getvalue(), srt_text


def _boundaries_to_srt(boundaries):
    """Chuyển WordBoundary events thành SRT."""
    def fmt_time(ticks):
        # ticks = 100-nanosecond units
        total_seconds = ticks / 10_000_000
        h = int(total_seconds // 3600)
        m = int((total_seconds % 3600) // 60)
        s = int(total_seconds % 60)
        ms = int((total_seconds - int(total_seconds)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    idx = 1
    # Gộp các word liên tiếp thành câu (kết thúc bởi dấu câu hoặc > 5s)
    group = []
    for b in boundaries:
        group.append(b)
        is_end = bool(re.search(r'[.!?…]$', b["text"].strip()))
        long_pause = len(group) > 1 and (b["offset"] + b["duration"] -
                                        group[0]["offset"]) > 50_000_000
        if is_end or long_pause:
            start = group[0]["offset"]
            end = group[-1]["offset"] + group[-1]["duration"]
            text = " ".join(x["text"] for x in group).strip()
            if text:
                lines.append(f"{idx}\n{fmt_time(start)} --> {fmt_time(end)}\n{text}\n")
                idx += 1
            group = []
    if group:
        start = group[0]["offset"]
        end = group[-1]["offset"] + group[-1]["duration"]
        text = " ".join(x["text"] for x in group).strip()
        if text:
            lines.append(f"{idx}\n{fmt_time(start)} --> {fmt_time(end)}\n{text}\n")
    return "\n".join(lines)


def edge_synthesize(text, voice, rate, pitch, volume, want_srt=False):
    """Wrapper đồng bộ."""
    return asyncio.run(_edge_synth_async(text, voice, rate, pitch, volume, want_srt))


# ============================================================
# VIENEU-TTS - CLONE GIỌNG
# ============================================================
class VieNeuEngine:
    """
    VieNeu-TTS: model TTS tiếng Việt với instant voice cloning.
    Chạy hoàn toàn trên CPU, không cần API key.
    """
    def __init__(self):
        self._tts = None

    def _load(self):
        if self._tts is None:
            from vieneu import Vieneu
            self._tts = Vieneu()  # tự tải model lần đầu (~vài trăm MB)
        return self._tts

    def clone_and_speak(self, text: str, ref_wav_path: str,
                        ref_text: str = "", speed: float = 1.0) -> bytes:
        """
        Sinh audio WAV từ text bằng giọng clone từ ref_wav_path.
        ref_text: nội dung chính xác của audio mẫu (giúp clone chính xác hơn).
        """
        tts = self._load()
        audio = tts.infer(
            text=text,
            ref_audio=ref_wav_path,
            ref_text=ref_text if ref_text else None,
        )
        buf = io.BytesIO()
        sf.write(buf, audio, 24000, format="WAV")
        return buf.getvalue()


def is_vieneu_available():
    """Kiểm tra xem vieneu đã cài chưa."""
    try:
        import vieneu  # noqa
        return True
    except ImportError:
        return False
