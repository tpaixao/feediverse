from PIL import Image, ImageDraw

def make_icon(size, path):
    img = Image.new('RGBA', (size, size), (15, 17, 23, 255))
    draw = ImageDraw.Draw(img)
    cx, cy = size * 0.5, size * 0.62
    accent = (76, 141, 255, 255)
    line_w = max(2, size // 64)
    for i, radius in enumerate([size*0.12, size*0.22, size*0.32]):
        bbox = [cx - radius, cy - radius, cx + radius, cy + radius]
        draw.arc(bbox, start=300, end=30, fill=accent, width=line_w + i*2)
    dot_r = size * 0.04
    draw.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r], fill=accent)
    img.save(path, 'PNG')
    print(f"Saved {path} ({size}x{size})")

make_icon(192, "static/icon-192.png")
make_icon(512, "static/icon-512.png")