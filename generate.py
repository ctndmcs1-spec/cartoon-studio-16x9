import asyncio
import edge_tts

# Nhập kịch bản muốn nói ở đây:
SCRIPT = "Chào các bạn! Đây là video hoạt hình 16:9 được tạo hoàn toàn tự động bằng code."
VOICE = "vi-VN-NamMinhNeural" # Giọng nam (hoặc vi-VN-HoaiMyNeural cho giọng nữ)

async def main():
    print(f"Đang tạo giọng nói cho: '{SCRIPT}'...")
    communicate = edge_tts.Communicate(SCRIPT, VOICE)
    await communicate.save("cartoon-app/public/audio.mp3")
    print("-> Đã tạo xong cartoon-app/public/audio.mp3!")

if __name__ == "__main__":
    asyncio.run(main())
