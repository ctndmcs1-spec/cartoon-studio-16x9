import streamlit as st
import os
import io

from voice_engine import (
    edge_synthesize, VieNeuEngine, is_vieneu_available,
)
from profile_manager import VoiceProfileManager
from subtitle_utils import clean_text, split_long_sentences
from document_utils import extract_text

# ============================================================
# CẤU HÌNH TRANG
# ============================================================
st.set_page_config(
    page_title="TTS + Voice Cloning",
    page_icon="🎙️",
    layout="wide",
)

# ============================================================
# KHỞI TẠO RESOURCE
# ============================================================
@st.cache_resource
def get_profile_manager():
    return VoiceProfileManager()

@st.cache_resource
def get_vieneu_engine():
    return VieNeuEngine()

pm = get_profile_manager()

# ============================================================
# DANH SÁCH GIỌNG CÓ SẴN (EDGE TTS)
# ============================================================
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
    "🎭 Bình thường": {"rate": "+0%", "pitch": "+0Hz", "volume": "+0%"},
    "😊 Vui vẻ": {"rate": "+15%", "pitch": "+20Hz", "volume": "+5%"},
    "🔥 Hào hứng": {"rate": "+25%", "pitch": "+30Hz", "volume": "+10%"},
    "😢 Buồn": {"rate": "-18%", "pitch": "-20Hz", "volume": "-15%"},
    "💧 Truyền cảm": {"rate": "-10%", "pitch": "-5Hz", "volume": "+0%"},
    "📖 Kể chuyện": {"rate": "-5%", "pitch": "+5Hz", "volume": "+0%"},
    "🧑‍🏫 Nghiêm túc": {"rate": "-8%", "pitch": "-10Hz", "volume": "+0%"},
    "🤫 Thì thầm": {"rate": "-25%", "pitch": "-15Hz", "volume": "-40%"},
    "📰 Tin tức": {"rate": "+5%", "pitch": "-5Hz", "volume": "+5%"},
}

# ============================================================
# HEADER
# ============================================================
st.title("🎙️ TTS + Voice Cloning")
st.caption("Giọng có sẵn (Edge TTS) · Sao chép giọng từ 10s ghi âm · Lưu & tái sử dụng")

# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.header("⚙️ Cấu hình")

    mode_options = ["🔊 Giọng có sẵn (Edge TTS)"]
    if is_vieneu_available():
        mode_options.append("🎤 Sao chép giọng (VieNeu-TTS)")
    else:
        st.warning(
            "⚠️ Chưa cài `vieneu`. Chạy lệnh:\n\n"
            "`pip install vieneu`\n\n"
            "để bật tính năng clone giọng."
        )

    mode = st.radio("Chế độ", mode_options)
    st.markdown("---")

    # ---------------- EDGE TTS ----------------
    if mode == "🔊 Giọng có sẵn (Edge TTS)":
        voice_label = st.selectbox("🗣️ Chọn giọng", list(VOICES.keys()))
        voice = VOICES[voice_label]
        emotion_label = st.selectbox("🎭 Cảm xúc", list(EMOTIONS.keys()))
        preset = EMOTIONS[emotion_label]

        rate_val = st.slider(
            "Tốc độ (%)", -50, 80,
            int(preset["rate"].replace("%", "").replace("+", "")),
        )
        pitch_val = st.slider(
            "Cao độ (Hz)", -50, 50,
            int(preset["pitch"].replace("Hz", "").replace("+", "")),
        )
        volume_val = st.slider(
            "Âm lượng (%)", -50, 50,
            int(preset["volume"].replace("%", "").replace("+", "")),
        )
        auto_clean = st.checkbox("🧹 Làm sạch văn bản", value=True)
        auto_split = st.checkbox("✂️ Chia câu dài", value=True)
        want_srt = st.checkbox("📝 Xuất phụ đề SRT", value=False)

    # ---------------- VOICE CLONING ----------------
    else:
        st.markdown("**🎤 Quản lý giọng đã lưu**")
        profiles = pm.list_profiles()
        if profiles:
            selected_profile = st.selectbox(
                "Chọn giọng đã lưu", ["— Tạo mới —"] + profiles
            )
        else:
            selected_profile = "— Tạo mới —"
            st.info("Chưa có giọng nào. Hãy tạo mới bên dưới.")

        if selected_profile != "— Tạo mới —":
            if st.button("🗑️ Xóa giọng này"):
                pm.delete_profile(selected_profile)
                st.rerun()

        st.markdown("---")
        st.markdown("**🎙️ Tạo giọng mới**")
        new_name = st.text_input("Tên giọng", placeholder="VD: Giong_Toi")
        new_desc = st.text_input("Mô tả (tùy chọn)", placeholder="VD: Giọng nam trầm")
        new_ref_text = st.text_input(
            "Nội dung trong file ghi âm (tùy chọn)",
            placeholder="VD: Xin chào, tôi tên là Minh.",
            help="Giúp clone chính xác hơn. Bỏ trống nếu không rõ.",
        )
        ref_audio = st.file_uploader(
            "Tải lên file ghi âm (WAV, 10-15 giây)",
            type=["wav", "mp3", "m4a", "ogg"],
        )
        if st.button("💾 Lưu giọng", type="primary"):
            if not new_name or not ref_audio:
                st.warning("Nhập tên và tải file ghi âm.")
            else:
                try:
                    wav_bytes = ref_audio.read()
                    path = pm.save_profile(
                        new_name, wav_bytes, new_desc, new_ref_text
                    )
                    st.success(f"✅ Đã lưu giọng '{new_name}'")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Lỗi: {e}")

# ============================================================
# TẢI VĂN BẢN TỪ FILE
# ============================================================
st.markdown("### 📝 Nhập văn bản")

col_up, col_btn = st.columns([3, 1])
with col_up:
    uploaded_doc = st.file_uploader(
        "Hoặc tải lên file PDF / DOCX / TXT để lấy nội dung",
        type=["pdf", "docx", "txt"],
        key="doc_uploader",
    )
with col_btn:
    st.write("")
    st.write("")
    if st.button("📋 Dùng ví dụ mẫu"):
        st.session_state["text_input"] = (
            "Xin chào! Mình là trợ lý giọng nói. "
            "Hôm nay bạn cảm thấy thế nào? "
            "Hy vọng công cụ này sẽ giúp ích cho bạn trong công việc và cuộc sống."
        )

# Xử lý file upload
if uploaded_doc is not None:
    try:
        text_from_file = extract_text(uploaded_doc.name, uploaded_doc.read())
        st.session_state["text_input"] = text_from_file
        st.success(f"✅ Đã trích xuất {len(text_from_file)} ký tự từ {uploaded_doc.name}")
    except Exception as e:
        st.error(f"❌ Không đọc được file: {e}")

text = st.text_area(
    "Văn bản",
    key="text_input",
    height=220,
    placeholder="Dán văn bản của bạn vào đây...",
    label_visibility="collapsed",
)

# ============================================================
# NÚT TẠO
# ============================================================
col1, col2 = st.columns([1, 1])
with col1:
    gen = st.button("🔊 Tạo giọng đọc", type="primary", use_container_width=True)

# ============================================================
# XỬ LÝ
# ============================================================
if gen:
    if not text.strip():
        st.warning("⚠️ Vui lòng nhập văn bản.")
    else:
        # ----- EDGE TTS -----
        if mode == "🔊 Giọng có sẵn (Edge TTS)":
            processed = text
            if auto_clean:
                processed = clean_text(processed)
            if auto_split:
                processed = split_long_sentences(processed)

            if not processed:
                st.error("❌ Không có nội dung hợp lệ sau khi xử lý.")
            else:
                rate = f"{'+' if rate_val >= 0 else ''}{rate_val}%"
                pitch = f"{'+' if pitch_val >= 0 else ''}{pitch_val}Hz"
                volume = f"{'+' if volume_val >= 0 else ''}{volume_val}%"

                with st.spinner("🎧 Đang tạo audio..."):
                    try:
                        audio, srt = edge_synthesize(
                            processed, voice, rate, pitch, volume,
                            want_srt=want_srt,
                        )
                        st.success(f"✅ Xong · {len(audio)/1024:.1f} KB")
                        st.audio(audio, format="audio/mpeg")
                        st.download_button(
                            "⬇️ Tải MP3", audio,
                            "output.mp3", "audio/mpeg",
                            use_container_width=True,
                        )
                        if srt:
                            st.download_button(
                                "⬇️ Tải SRT", srt,
                                "output.srt", "text/plain",
                                use_container_width=True,
                            )
                            with st.expander("📝 Xem phụ đề SRT"):
                                st.code(srt, language="text")
                        with st.expander("🔍 Văn bản sau khi xử lý"):
                            st.write(processed)
                    except Exception as e:
                        st.error(f"❌ Lỗi: {e}")

        # ----- VOICE CLONING -----
        else:
            if selected_profile == "— Tạo mới —":
                st.warning("⚠️ Chọn một giọng đã lưu hoặc tạo mới trước.")
            else:
                ref_path, meta = pm.get_profile(selected_profile)
                if not ref_path:
                    st.error("❌ Không tìm thấy file giọng.")
                else:
                    processed = clean_text(text)
                    ref_text = meta.get("ref_text", "")

                    with st.spinner(f"🎤 Đang clone giọng '{selected_profile}'..."):
                        try:
                            engine = get_vieneu_engine()
                            audio = engine.clone_and_speak(
                                processed, ref_path, ref_text=ref_text,
                            )
                            st.success(f"✅ Xong · {len(audio)/1024:.1f} KB")
                            st.audio(audio, format="audio/wav")
                            st.download_button(
                                "⬇️ Tải WAV", audio,
                                "output.wav", "audio/wav",
                                use_container_width=True,
                            )
                        except Exception as e:
                            st.error(f"❌ Lỗi: {e}")
                            st.info(
                                "💡 Nếu báo 'Out of Memory', thử khởi động lại app "
                                "hoặc dùng Edge TTS cho văn bản ngắn."
                            )

# ============================================================
# HƯỚNG DẪN (dùng biến string riêng, KHÔNG triple-quote lồng)
# ============================================================
HUONG_DAN_GHI_AM = """
### 🎙️ Cách ghi âm để clone giọng chất lượng:

1. **Thời lượng**: 10–15 giây (VieNeu cần 3–5s)
2. **Môi trường**: Yên tĩnh, không tiếng ồn, không nhạc nền
3. **Nội dung**: Nói câu hoàn chỉnh, tự nhiên, đủ dấu câu.
   Ví dụ: *"Xin chào, tôi tên là Minh. Hôm nay trời đẹp, tôi rất vui."*
4. **Giọng điệu**: Trung tính, không quá nhanh/quá chậm
5. **Định dạng**: WAV, MP3, M4A đều được (24kHz mono tốt nhất)
6. **Micro**: Cách miệng 15–20cm, tránh gió và tiếng thở

### ⚠️ Lưu ý:
- Chỉ clone giọng của **chính bạn** hoặc có sự cho phép
- Streamlit Cloud free tier giới hạn RAM ~1GB
- Thư mục `profiles/` có thể mất khi app restart trên Cloud
"""

HUONG_DAN_DEPLOY = """
### Chạy local

Mở terminal và chạy:

    pip install -r requirements.txt
    streamlit run app.py

Muốn dùng voice cloning, cài thêm:

    pip install vieneu

### Deploy Streamlit Cloud

1. Push repo lên GitHub
2. Vào https://share.streamlit.io → **New app**
3. Chọn repo, main file `app.py`, bấm **Deploy**
4. Đảm bảo file `packages.txt` có: `espeak-ng`, `ffmpeg`, `libsndfile1`
5. Nếu muốn voice cloning, thêm `vieneu` vào `requirements.txt`

### Cấu trúc file

- `app.py` — UI chính
- `voice_engine.py` — Edge TTS + VieNeu-TTS
- `profile_manager.py` — Quản lý voice profiles
- `subtitle_utils.py` — Làm sạch văn bản + SRT
- `document_utils.py` — Đọc PDF/DOCX/TXT
- `requirements.txt` — Thư viện Python
- `packages.txt` — Gói hệ thống cho Cloud
"""

with st.expander("💡 Hướng dẫn ghi âm để clone giọng chuẩn"):
    st.markdown(HUONG_DAN_GHI_AM)

with st.expander("🔧 Cài đặt & Deploy"):
    st.markdown(HUONG_DAN_DEPLOY)
