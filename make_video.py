import asyncio
import os
import numpy as np
from PIL import Image, ImageDraw
import edge_tts
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, concatenate_videoclips

# 1. KỊCH BẢN MUỐN NÓI
TEXT = "Chào các bạn! Đây là video hoạt hình 16:9 làm tự động hoàn toàn bằng Python trên điện thoại."
VOICE = "vi-VN-NamMinhNeural"

async def gen_voice():
    communicate = edge_tts.Communicate(TEXT, VOICE)
    await communicate.save("audio.mp3")

# 2. TỰ ĐỘNG TẠO HÌNH NHÂN VẬT & TÁCH NỀN
def prepare_assets():
    os.makedirs("assets", exist_ok=True)
    if os.path.exists("nhanvat.jpg"):
        from rembg import remove
        img = Image.open("nhanvat.jpg")
        remove(img).save("assets/body.png", "PNG")
    else:
        # Nếu chưa có ảnh thì vẽ tạm 1 nhân vật tròn màu vàng để test
        img = Image.new("RGBA", (300, 400), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([50, 80, 250, 350], fill=(255, 204, 0, 255))
        draw.ellipse([80, 130, 110, 170], fill=(0, 0, 0, 255))
        draw.ellipse([190, 130, 220, 170], fill=(0, 0, 0, 255))
        img.save("assets/body.png", "PNG")

    m_open = Image.new("RGBA", (80, 50), (0, 0, 0, 0))
    m_close = Image.new("RGBA", (80, 50), (0, 0, 0, 0))
    ImageDraw.Draw(m_open).ellipse([10, 10, 70, 40], fill=(220, 50, 50, 255))
    ImageDraw.Draw(m_close).line([(15, 25), (65, 25)], fill=(0, 0, 0, 255), width=5)
    m_open.save("assets/mouth_open.png")
    m_close.save("assets/mouth_close.png")

# 3. DỰNG VIDEO CHUẨN 16:9 (1920x1080)
def create_video():
    prepare_assets()
    asyncio.run(gen_voice())

    audio = AudioFileClip("audio.mp3")
    duration = audio.duration

    bg = ImageClip(np.zeros((1080, 1920, 3), dtype=np.uint8) + np.array([30, 41, 59], dtype=np.uint8)).set_duration(duration)

    body = (ImageClip("assets/body.png")
            .set_duration(duration)
            .set_position(lambda t: (350, 350 + int(np.sin(t * 10) * 12))))

    m_o = ImageClip("assets/mouth_open.png").set_duration(0.15)
    m_c = ImageClip("assets/mouth_close.png").set_duration(0.15)
    mouth_loop = concatenate_videoclips([m_o, m_c] * int(duration / 0.3 + 2)).set_duration(duration)
    mouth = mouth_loop.set_position(lambda t: (460, 560 + int(np.sin(t * 10) * 12)))

    final = CompositeVideoClip([bg, body, mouth], size=(1920, 1080)).set_audio(audio).set_duration(duration)
    final.write_videofile("video_xuat.mp4", fps=24, codec="libx264", audio_codec="aac")
    print("DONE_VIDEO_XUAT")

if __name__ == "__main__":
    create_video()
