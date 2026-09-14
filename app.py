import streamlit as st
import edge_tts
import asyncio
import re
import io
import os

from voice_clone import VieNeuBackend, XTTSBackend, VoiceProfileManager

st.set_page_config(
    page_title="TTS + Voice Cloning",
    page_icon="🎙️",
    layout="wide",
)

# ============ KHỞI TẠO ============
@st.cache_resource
def get_profile_manager():
    return VoiceProfileManager()

@st.cache_resource
def get_vieneu():
    return VieNeuBackend()

@st.cache_resource
def get_xtts():
    return XTTSBackend()

pm = get_profile_manager()

# ============ DANH SÁCH GIỌNG CÓ SẴN (EDGE TTS) ============
VOICES = {
    "🇻🇳 Hoài My (Nữ)": "vi-VN-HoaiMyNeural",
    "🇻🇳 Nam Minh (Nam)": "vi-VN-NamMinhNeural",
    "🇺🇸 Aria (Nữ)": "en-US-AriaNeural",
    "🇺🇸 Guy (Nam)": "en-US-GuyNeural",
    "🇬🇧 Sonia (Nữ)": "en-GB-SoniaNeural",
    "🇨🇳 Xiaoxiao (Nữ)": "zh-CN-XiaoxiaoNeural",
    "🇯🇵 Nanami (Nữ)": "ja-JP-NanamiNeural",
    "🇰🇷 SunHi (Nữ)": "ko-KR-SunHiNeural",
}

EMOTIONS = {
    "🎭 Bình thường":   {"rate": "+0%",  "pitch": "+0Hz",  "volume": "+0%"},
    "😊 Vui vẻ":        {"rate": "+15%", "pitch": "+20Hz", "volume": "+5%"},
    "🔥 Hào hứng":      {"rate": "+25%", "pitch": "+30Hz", "volume": "+10%"},
    "😢 Buồn":          {"rate": "-18%", "pitch": "-20Hz", "volume": "-15%"},
    "💧 Truyền cảm":    {"rate": "-10%", "pitch": "-5Hz",  "volume": "+0%"},
    "📖 Kể chuyện":     {"rate": "-5%",  "pitch": "+5Hz",  "volume": "+0%"},
    "🧑‍🏫 Nghiêm túc":   {"rate": "-8%",  "pitch": "-10Hz", "volume": "+0%"},
    "🤫 Thì thầm":      {"rate": "-25%", "pitch": "-15Hz", "volume": "-40%"},
}

# ============ TEXT CLEANING ============
def clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line[-1] not in ".!?;:,…":
            line += "."
        lines.append(line)
    text = " ".join(lines)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"[^\w\s\.,!\?;:…àáảãạăằắẳẵặâầấẩẫậđèéẻẽẹêềếểễệ"
                  r"ìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ"
                  r"\-–—\(\)\[\]\"'\/%&\n]", " ", text, flags=re.UNICODE)
    text = re.sub(r"([,.!?;:])\1+", r"\1", text)
    text = re.sub(r"\s+([,.!?;:…])", r"\1", text)
    text = re.sub(r"([,.!?;:])(?=[^\s\d])", r"\1 ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def split_long_sentences(text: str, max_len: int = 180) -> str:
    parts = re.split(r"(?<=[.!?…])\s+", text)
    result = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if len(p) <= max_len:
            result.append(p)
            continue
        sub = re.split(r"(?<=[,;:])\s+", p)
        cur = ""
        for s in sub:
            if len(cur) + len(s) + 1 <= max_len:
                cur = (cur + " " + s).strip()
            else:
                if cur:
                    result.append(cur)
                cur = s
        if cur:
            result.append(cur)
    return " ".join(result)

# ============ EDGE TTS ============
async def _edge_synth(text, voice, rate, pitch, volume):
    communicate = edge_tts.Communicate(text=text, voice=voice,
                                       rate=rate, pitch=pitch, volume=volume)
    buf = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    return buf.getvalue()

def edge_synthesize(text, voice, rate, pitch, volume) -> bytes:
    return asyncio.run(_edge_synth(text, voice, rate, pitch, volume))


# ============ UI ============
st.title("🎙️ TTS + Voice Cloning")
st.caption("Giọng có sẵn (Edge TTS) · Sao chép giọng từ 10s ghi âm · Lưu & tái sử dụng")

# Sidebar: chế độ
with st.sidebar:
    st.header("⚙️ Cấu hình")
    mode = st.radio("Chế độ", [
        "🔊 Giọng có sẵn (Edge TTS)",
        "🎤 Sao chép giọng (Voice Cloning)",
    ])

    st.markdown("---")

    if mode == "🔊 Giọng có sẵn (Edge TTS)":
        voice_label = st.selectbox("🗣️ Chọn giọng", list(VOICES.keys()))
        voice = VOICES[voice_label]
        emotion_label = st.selectbox("🎭 Cảm xúc", list(EMOTIONS.keys()))
        preset = EMOTIONS[emotion_label]

        rate_val = st.slider("Tốc độ (%)", -50, 80,
                             int(preset["rate"].replace("%", "").replace("+", "")))
        pitch_val = st.slider("Cao độ (Hz)", -50, 50,
                              int(preset["pitch"].replace("Hz", "").replace("+", "")))
        volume_val = st.slider("Âm lượng (%)", -50, 50,
                               int(preset["volume"].replace("%", "").replace("+", "")))
        auto_clean = st.checkbox("🧹 Làm sạch văn bản", value=True)
        auto_split = st.checkbox("✂️ Chia câu dài", value=True)

    else:
        # Chế độ voice cloning
        backend_name = st.selectbox("🧠 Backend", [
            "VieNeu-TTS (nhẹ, tiếng Việt, CPU)",
            "Coqui XTTS v2 (nặng, đa ngôn ngữ)",
        ])
        st.markdown("---")
        st.markdown("**🎤 Quản lý giọng đã lưu**")
        profiles = pm.list_profiles()
        if profiles:
            selected_profile = st.selectbox("Chọn giọng đã lưu", ["— Tạo mới —"] + profiles)
        else:
            selected_profile = "— Tạo mới —"
            st.info("Chưa có giọng nào. Hãy tạo mới bên dưới.")

        if selected_profile != "— Tạo mới —" and st.button("🗑️ Xóa giọng này"):
            pm.delete_profile(selected_profile)
            st.rerun()

        st.markdown("---")
        st.markdown("**🎙️ Tạo giọng mới**")
        new_name = st.text_input("Tên giọng", placeholder="VD: Giong_Toi")
        new_desc = st.text_input("Mô tả (tùy chọn)", placeholder="VD: Giọng nam trầm")
        ref_audio = st.file_uploader(
            "Tải lên file ghi âm (WAV, 10-15 giây, nói rõ ràng)",
            type=["wav", "mp3", "m4a", "ogg"],
        )
        if st.button("💾 Lưu giọng", type="primary"):
            if not new_name or not ref_audio:
                st.warning("Nhập tên và tải file ghi âm.")
            else:
                try:
                    wav_bytes = ref_audio.read()
                    path = pm.save_profile(new_name, wav_bytes, new_desc)
                    st.success(f"✅ Đã lưu giọng '{new_name}' → {path}")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Lỗi: {e}")

# ============ VÙNG NHẬP VĂN BẢN ============
st.markdown("### 📝 Nhập văn bản")
text = st.text_area(
    "Văn bản",
    height=200,
    placeholder="Dán văn bản của bạn vào đây...",
    label_visibility="collapsed",
)

col1, col2 = st.columns([1, 1])
with col1:
    gen = st.button("🔊 Tạo giọng đọc", type="primary", use_container_width=True)

# ============ XỬ LÝ ============
if gen:
    if not text.strip():
        st.warning("⚠️ Nhập văn bản.")
    else:
        processed = text
        if mode == "🔊 Giọng có sẵn (Edge TTS)":
            if auto_clean:
                processed = clean_text(processed)
            if auto_split:
                processed = split_long_sentences(processed)

        if mode == "🔊 Giọng có sẵn (Edge TTS)":
            rate = f"{'+' if rate_val >= 0 else ''}{rate_val}%"
            pitch = f"{'+' if pitch_val >= 0 else ''}{pitch_val}Hz"
            volume = f"{'+' if volume_val >= 0 else ''}{volume_val}%"
            with st.spinner("🎧 Đang tạo..."):
                try:
                    audio = edge_synthesize(processed, voice, rate, pitch, volume)
                    st.success("✅ Xong!")
                    st.audio(audio, format="audio/mpeg")
                    st.download_button("⬇️ Tải MP3", audio, "output.mp3", "audio/mpeg")
                except Exception as e:
                    st.error(f"❌ Lỗi: {e}")

        else:
            # Voice cloning
            if selected_profile == "— Tạo mới —":
                st.warning("Chọn một giọng đã lưu hoặc tạo mới trước.")
            else:
                ref_path, meta = pm.get_profile(selected_profile)
                if not ref_path:
                    st.error("Không tìm thấy file giọng.")
                else:
                    # Xử lý văn bản cho backend
                    if backend_name.startswith("VieNeu"):
                        processed = clean_text(processed) if 'clean_text' in dir() else processed
                    with st.spinner(f"🎤 Đang clone giọng '{selected_profile}'..."):
                        try:
                            if backend_name.startswith("VieNeu"):
                                engine = get_vieneu()
                                audio = engine.clone_and_speak(processed, ref_path)
                                fmt = "audio/wav"
                                fname = "output.wav"
                            else:
                                engine = get_xtts()
                                lang = st.selectbox("Ngôn ngữ", ["vi", "en", "zh-cn", "ja", "ko"]) if 'lang' not in dir() else "vi"
                                audio = engine.clone_and_speak(processed, ref_path, language="vi")
                                fmt = "audio/wav"
                                fname = "output.wav"
                            st.success("✅ Xong!")
                            st.audio(audio, format=fmt)
                            st.download_button(f"⬇️ Tải {fname}", audio, fname, fmt)
                        except Exception as e:
                            st.error(f"❌ Lỗi: {e}")
                            st.info("💡 Nếu lỗi 'Out of Memory', thử backend VieNeu-TTS hoặc nâng cấp Streamlit Cloud.")

# ============ HƯỚNG DẪN ============
with st.expander("💡 Hướng dẫn ghi âm để clone giọng chuẩn"):
    st.markdown("""
    ### 🎙️ Cách ghi âm để có giọng clone chất lượng:
    1. **Thời lượng**: 10–15 giây (VieNeu cần 3–5s, XTTS cần 10–30s)
    2. **Môi trường**: Yên tĩnh, không tiếng ồn, không nhạc nền
    3. **Nội dung**: Nói câu hoàn chỉnh, tự nhiên, đủ dấu câu
       - Ví dụ: *"Xin chào, tôi tên là Minh. Hôm nay trời đẹp, tôi rất vui."*
    4. **Giọng điệu**: Nói với cảm xúc trung tính, không quá nhanh/quá chậm
    5. **Định dạng**: WAV, MP3, M4A đều được (24kHz mono là tốt nhất)
    6. **Micro**: Cách miệng 15–20cm, tránh gió và tiếng thở

    ### ⚠️ Lưu ý:
    - Chỉ clone giọng của **chính bạn** hoặc có sự cho phép
    - Streamlit Cloud free tier giới hạn RAM ~1GB
    - Nếu model XTTS báo lỗi RAM, dùng **VieNeu-TTS** (nhẹ hơn nhiều)
    """)

with st.expander("🔧 Cài đặt & Deploy"):
    st.markdown("""
    ### Chạy local:
    ```bash
    pip install -r requirements.txt
    streamlit run app.py
