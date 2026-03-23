from PIL import Image, ImageDraw, ImageFont

def make_icon():
    sizes = [256, 128, 64, 48, 32, 16]
    frames = []
    for size in sizes:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        pad = max(2, size // 16)
        r = size // 5
        draw.rounded_rectangle([pad, pad, size-pad, size-pad], radius=r, fill="#1a1a2e")
        font_size = max(8, size // 3)
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except:
            font = ImageFont.load_default()
        text_i = "I"
        text_b = "B"
        bbox_i = draw.textbbox((0,0), text_i, font=font)
        bbox_b = draw.textbbox((0,0), text_b, font=font)
        w_i = bbox_i[2] - bbox_i[0]
        h   = bbox_i[3] - bbox_i[1]
        total_w = w_i + (bbox_b[2] - bbox_b[0])
        x = (size - total_w) // 2
        y = (size - h) // 2 - bbox_i[1]
        draw.text((x,       y), text_i, fill="#ffffff", font=font)
        draw.text((x + w_i, y), text_b, fill="#3b82f6", font=font)
        frames.append(img)
    frames[0].save("invobiz.ico", format="ICO",
                   sizes=[(s,s) for s in sizes],
                   append_images=frames[1:])
    print("invobiz.ico created.")

if __name__ == "__main__":
    make_icon()
