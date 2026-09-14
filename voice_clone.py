"""
Voice Cloning Engine — hỗ trợ nhiều backend.
Mặc định: VieNeu-TTS (nhẹ, chạy CPU, tiếng Việt tốt).
Tùy chọn: Coqui XTTS v2 (nặng, đa ngôn ngữ).
"""
import os
import json
import io
import numpy as np
import soundfile as sf

PROFILES_DIR = "profiles"
os.makedirs(PROFILES_DIR, exist_ok=True)


# ============================================================
# BACKEND 1: VieNeu-TTS (khuyên dùng cho Streamlit Cloud free)
# ============================================================
class VieNeuBackend:
    """
    VieNeu-TTS: model TTS tiếng Việt với instant voice cloning.
    Clone chỉ với 3-5 giây audio tham chiếu. Chạy hoàn toàn trên CPU.
    """
    def __init__(self):
        self._tts = None

    def _load(self):
        if self._tts is None:
            from vieneu import Vieneu
            self._tts = Vieneu()  # Tự tải model lần đầu (~100MB)
        return self._tts

    def clone_and_speak(self, text: str, ref_wav_path: str, speed: float = 1.0) -> bytes:
        """
        Sinh audio từ text bằng giọng clone từ ref_wav_path.
        Trả về bytes WAV.
        """
        tts = self._load()
        audio = tts.infer(
            text=text,
            ref_audio=ref_wav_path,
            speed=speed,
        )
        # Lưu ra buffer
        buf = io.BytesIO()
        sf.write(buf, audio, 24000, format="WAV")
        return buf.getvalue()


# ============================================================
# BACKEND 2: Coqui XTTS v2 (chất lượng cao, đa ngôn ngữ)
# ============================================================
class XTTSBackend:
    """
    Coqui XTTS v2: zero-shot voice cloning đa ngôn ngữ.
    Cần ~2GB RAM. Khuyên dùng khi có GPU hoặc RAM >= 4GB.
    """
    def __init__(self, model_name="tts_models/multilingual/multi-dataset/xtts_v2"):
        self.model_name = model_name
        self._tts = None

    def _load(self):
        if self._tts is None:
            from TTS.api import TTS
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self._tts = TTS(self.model_name).to(device)
        return self._tts

    def clone_and_speak(
        self,
        text: str,
        ref_wav_path: str,
        language: str = "vi",
        speed: float = 1.0,
        emotion: str = "neutral",
    ) -> bytes:
        """
        Sinh audio từ text bằng giọng clone.
        emotion: neutral | happy | sad | angry | surprised | fearful
        """
        tts = self._load()
        # XTTS v2 hỗ trợ emotion qua tham số style_wav (nếu có)
        out_path = os.path.join(PROFILES_DIR, "_tmp_output.wav")
        tts.tts_to_file(
            text=text,
            speaker_wav=ref_wav_path,
            language=language,
            file_path=out_path,
            speed=speed,
        )
        with open(out_path, "rb") as f:
            data = f.read()
        os.remove(out_path)
        return data


# ============================================================
# QUẢN LÝ VOICE PROFILES
# ============================================================
class VoiceProfileManager:
    """
    Lưu/tải voice profiles. Mỗi profile gồm:
    - profiles/<name>/ref.wav  : audio tham chiếu (10s)
    - profiles/<name>/meta.json: metadata
    """
    def __init__(self, base_dir=PROFILES_DIR):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

    def save_profile(self, name: str, ref_wav_bytes: bytes, description: str = "") -> str:
        """Lưu profile mới. Trả về đường dẫn ref.wav."""
        safe_name = "".join(c for c in name if c.isalnum() or c in "-_ ").strip()
        if not safe_name:
            raise ValueError("Tên profile không hợp lệ.")
        pdir = os.path.join(self.base_dir, safe_name)
        os.makedirs(pdir, exist_ok=True)

        # Lưu WAV
        wav_path = os.path.join(pdir, "ref.wav")
        # Chuẩn hóa về 24kHz mono
        audio, sr = sf.read(io.BytesIO(ref_wav_bytes))
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if sr != 24000:
            import librosa
            audio = librosa.resample(audio, orig_sr=sr, target_sr=24000)
        sf.write(wav_path, audio, 24000)

        # Lưu metadata
        meta = {
            "name": safe_name,
            "description": description,
            "duration_sec": round(len(audio) / 24000, 2),
            "sample_rate": 24000,
        }
        with open(os.path.join(pdir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        return wav_path

    def list_profiles(self):
        """Trả về danh sách tên profile."""
        if not os.path.isdir(self.base_dir):
            return []
        return [
            d for d in sorted(os.listdir(self.base_dir))
            if os.path.isdir(os.path.join(self.base_dir, d))
            and os.path.exists(os.path.join(self.base_dir, d, "ref.wav"))
        ]

    def get_profile(self, name: str):
        """Trả về (wav_path, meta_dict) hoặc (None, None)."""
        pdir = os.path.join(self.base_dir, name)
        wav_path = os.path.join(pdir, "ref.wav")
        meta_path = os.path.join(pdir, "meta.json")
        if not os.path.exists(wav_path):
            return None, None
        meta = {}
        if os.path.exists(meta_path):
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
        return wav_path, meta

    def delete_profile(self, name: str):
        import shutil
        pdir = os.path.join(self.base_dir, name)
        if os.path.isdir(pdir):
            shutil.rmtree(pdir)
