from rembg import remove
from PIL import Image, ImageDraw
import os

def process_character(input_image_path):
    os.makedirs("cartoon-app/public/assets", exist_ok=True)
    
    if not os.path.exists(input_image_path):
        print(f"Lỗi: Không tìm thấy file {input_image_path}")
        return
        
    print("AI đang quét và tự động tách nền...")
    img = Image.open(input_image_path)
    
    # Tách nền thân nhân vật
    body_no_bg = remove(img)
    body_no_bg.save("cartoon-app/public/assets/body.png", "PNG")
    print("-> Đã tạo: body.png (thân nhân vật)")

    # Tạo khẩu hình miệng mở / đóng cơ bản
    mouth_open = Image.new("RGBA", (100, 60), (255, 255, 255, 0))
    mouth_close = Image.new("RGBA", (100, 60), (255, 255, 255, 0))
    
    draw_open = ImageDraw.Draw(mouth_open)
    draw_open.ellipse([10, 10, 90, 50], fill=(200, 50, 50, 255))
    mouth_open.save("cartoon-app/public/assets/mouth_open.png", "PNG")

    draw_close = ImageDraw.Draw(mouth_close)
    draw_close.line([(15, 30), (85, 30)], fill=(50, 50, 50, 255), width=5)
    mouth_close.save("cartoon-app/public/assets/mouth_close.png", "PNG")
    
    print("-> Đã chuẩn bị xong toàn bộ bộ phận!")

if __name__ == "__main__":
    process_character("nhanvat.jpg")
