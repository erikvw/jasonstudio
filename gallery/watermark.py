from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def apply_watermark(
    image_file: BytesIO,
    text: str = "PROOF",
    opacity: int = 80,
) -> BytesIO:
    img = Image.open(image_file).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font_size = max(img.size[0] // 10, 40)
    try:
        font = ImageFont.truetype("Arial", font_size)
    except OSError:
        font = ImageFont.load_default(size=font_size)

    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    step_x = text_w + font_size * 2
    step_y = text_h + font_size * 2

    y = -text_h
    while y < img.size[1] + text_h:
        x = -text_w
        while x < img.size[0] + text_w:
            draw.text((x, y), text, font=font, fill=(255, 255, 255, opacity))
            x += step_x
        y += step_y

    watermarked = Image.alpha_composite(img, overlay).convert("RGB")

    output = BytesIO()
    output_format = _guess_format(Path(image_file.name).suffix if hasattr(image_file, "name") else ".jpg")
    watermarked.save(output, format=output_format, quality=85)
    output.seek(0)
    return output


def _guess_format(suffix: str) -> str:
    return {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG"}.get(
        suffix.lstrip(".").lower(), "JPEG"
    )
