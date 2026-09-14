"""
Quản lý Voice Profiles - lưu giọng đã clone để tái sử dụng.
"""
import os
import io
import json
import shutil
import numpy as np
import soundfile as sf

PROFILES_DIR = "profiles"
os.makedirs(PROFILES_DIR, exist_ok=True)


class VoiceProfileManager:
    def __init__(self, base_dir=PROFILES_DIR):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

    def save_profile(self, name: str, ref_wav_bytes: bytes,
                     description: str = "", ref_text: str = "") -> str:
        """Lưu profile mới. Trả về đường dẫn ref.wav."""
        safe_name = "".join(c for c in name
                            if c.isalnum() or c in "-_ ").strip()
        if not safe_name:
            raise ValueError("Tên profile không hợp lệ.")

        pdir = os.path.join(self.base_dir, safe_name)
        os.makedirs(pdir, exist_ok=True)

        wav_path = os.path.join(pdir, "ref.wav")
        audio, sr = sf.read(io.BytesIO(ref_wav_bytes))
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if sr != 24000:
            try:
                import librosa
                audio = librosa.resample(audio, orig_sr=sr, target_sr=24000)
            except Exception:
                pass  # giữ nguyên nếu librosa lỗi
        sf.write(wav_path, audio, 24000)

        meta = {
            "name": safe_name,
            "description": description,
            "ref_text": ref_text,
            "duration_sec": round(len(audio) / 24000, 2),
            "sample_rate": 24000,
        }
        with open(os.path.join(pdir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return wav_path

    def list_profiles(self):
        if not os.path.isdir(self.base_dir):
            return []
        return [
            d for d in sorted(os.listdir(self.base_dir))
            if os.path.isdir(os.path.join(self.base_dir, d))
            and os.path.exists(os.path.join(self.base_dir, d, "ref.wav"))
        ]

    def get_profile(self, name: str):
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
        pdir = os.path.join(self.base_dir, name)
        if os.path.isdir(pdir):
            shutil.rmtree(pdir)
