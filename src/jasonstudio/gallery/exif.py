from datetime import datetime
from io import BytesIO
from typing import Any

from PIL import Image, ImageOps
from PIL.ExifTags import TAGS


def extract_exif(image_file: BytesIO) -> dict[str, Any]:
    data: dict[str, Any] = {}
    try:
        img = ImageOps.exif_transpose(Image.open(image_file))
        data["image_width"] = img.width
        data["image_height"] = img.height

        exif_raw = img.getexif()
        if not exif_raw:
            return data

        exif = {TAGS.get(k, k): v for k, v in exif_raw.items()}

        # Camera model
        make = str(exif.get("Make", "")).strip()
        model = str(exif.get("Model", "")).strip()
        if model and make and not model.startswith(make):
            data["camera_model"] = f"{make} {model}"
        elif model:
            data["camera_model"] = model
        elif make:
            data["camera_model"] = make

        # Date taken
        for tag in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
            raw = exif.get(tag)
            if raw:
                try:
                    data["date_taken"] = datetime.strptime(
                        str(raw), "%Y:%m:%d %H:%M:%S"
                    )
                except ValueError, TypeError:
                    pass
                break

        # Focal length
        fl = exif.get("FocalLength")
        if fl:
            data["focal_length"] = f"{_rational_to_float(fl):.0f}mm"

        # Aperture (FNumber)
        fn = exif.get("FNumber")
        if fn:
            data["aperture"] = f"f/{_rational_to_float(fn):.1f}"

        # Shutter speed (ExposureTime)
        et = exif.get("ExposureTime")
        if et:
            val = _rational_to_float(et)
            if val and val < 1:
                data["shutter_speed"] = f"1/{int(1 / val)}s"
            elif val:
                data["shutter_speed"] = f"{val:.1f}s"

        # ISO
        iso = exif.get("ISOSpeedRatings")
        if iso:
            data["iso"] = str(iso)

    except Exception:
        pass

    return data


def _rational_to_float(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        if value.denominator:
            return value.numerator / value.denominator
    try:
        return float(value)
    except TypeError, ValueError:
        return 0.0
