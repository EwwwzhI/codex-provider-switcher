from pathlib import Path

from PIL import Image


root = Path(__file__).resolve().parents[1]
source = root / "provider_switcher" / "assets" / "app-icon.png"
target = source.with_suffix(".ico")
sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

with Image.open(source) as original:
    image = original.convert("RGBA")
    if image.width != image.height:
        edge = min(image.size)
        left = (image.width - edge) // 2
        top = (image.height - edge) // 2
        image = image.crop((left, top, left + edge, top + edge))
    if image.size != (1024, 1024):
        image = image.resize((1024, 1024), Image.Resampling.LANCZOS)
    image.save(source, "PNG", optimize=True)
    image.save(target, "ICO", sizes=sizes)

print(f"Generated {target} with {len(sizes)} sizes")
