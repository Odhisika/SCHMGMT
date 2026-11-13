import os
import re
from PIL import Image, ImageDraw, ImageColor
from django.conf import settings
from django.contrib.staticfiles import finders


def link_callback(uri, rel):
    """
    Convert HTML URIs to absolute system paths so xhtml2pdf can access those resources.
    """
    # If already an existing absolute file path, return it directly
    if os.path.isabs(uri) and os.path.exists(uri):
        return uri

    # If it is a media file URL
    if uri.startswith(settings.MEDIA_URL):
        path = os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, ""))
        if os.path.exists(path):
            return path

    # If it is a static file URL
    if uri.startswith(settings.STATIC_URL):
        path = os.path.join(
            settings.STATIC_ROOT or os.path.join(settings.BASE_DIR, "static"),
            uri.replace(settings.STATIC_URL, ""),
        )
        if os.path.exists(path):
            return path

    # Try staticfiles finders for relative paths
    try:
        result = finders.find(uri)
        if result:
            if not isinstance(result, (list, tuple)):
                result = [result]
            return result[0]
    except Exception:
        pass

    # Fallback to static root
    sRoot = settings.STATIC_ROOT or os.path.join(settings.BASE_DIR, "static")
    fallback_path = os.path.join(sRoot, uri)
    if os.path.exists(fallback_path):
        return fallback_path

    return uri


def clean_hex_color(color_str, default="#0c2340"):
    """Validate and clean hex color string."""
    if not color_str:
        return default
    color_str = color_str.strip()
    if not color_str.startswith("#"):
        color_str = "#" + color_str
    if re.match(r"^#[0-9a-fA-F]{6}$", color_str) or re.match(
        r"^#[0-9a-fA-F]{3}$", color_str
    ):
        return color_str
    return default


def get_school_document_frame(school=None):
    """
    Generates or retrieves a clean, vector-rendered A4 document frame
    using the school's native primary and secondary colors set by the admin.
    Cached by school ID and color values so it re-generates automatically
    whenever an admin updates the school theme colors.
    """
    primary_hex = clean_hex_color(
        getattr(school, "primary_color", None) if school else None, "#0c2340"
    )
    secondary_hex = clean_hex_color(
        getattr(school, "secondary_color", None) if school else None, "#7cb342"
    )

    school_key = str(getattr(school, "id", "default")) if school else "default"
    color_tag = f"{primary_hex.replace('#', '')}_{secondary_hex.replace('#', '')}"
    filename = f"school_frame_{school_key}_{color_tag}.png"

    cache_dir = os.path.join(settings.MEDIA_ROOT, "school_frames")
    os.makedirs(cache_dir, exist_ok=True)
    out_path = os.path.join(cache_dir, filename)

    if os.path.exists(out_path):
        return out_path

    # Generate crisp supersampled frame
    W, H = 2480, 3508
    img = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    try:
        c_pri = ImageColor.getrgb(primary_hex)
    except Exception:
        c_pri = (12, 35, 64)

    try:
        c_sec = ImageColor.getrgb(secondary_hex)
    except Exception:
        c_sec = (124, 179, 66)

    def bezier_curve(p0, p1, p2, p3, steps=100):
        res = []
        for i in range(steps + 1):
            t = i / steps
            u = 1 - t
            x = (
                u**3 * p0[0]
                + 3 * u**2 * t * p1[0]
                + 3 * u * t**2 * p2[0]
                + t**3 * p3[0]
            )
            y = (
                u**3 * p0[1]
                + 3 * u**2 * t * p1[1]
                + 3 * u * t**2 * p2[1]
                + t**3 * p3[1]
            )
            res.append((int(x), int(y)))
        return res

    # 1. Top-Right Waves
    # Primary wave
    b_pri_tr = bezier_curve(
        (int(W * 0.83), 0),
        (int(W * 0.89), int(H * 0.08)),
        (int(W * 0.95), int(H * 0.17)),
        (W, int(H * 0.28)),
    )
    draw.polygon([(int(W * 0.83), 0)] + b_pri_tr + [(W, 0)], fill=c_pri)

    # Secondary ribbon with tapered tip
    b_sec_tr_left = bezier_curve(
        (int(W * 0.72), 0),
        (int(W * 0.79), int(H * 0.08)),
        (int(W * 0.88), int(H * 0.18)),
        (int(W * 0.99), int(H * 0.27)),
    )
    b_sec_tr_right = bezier_curve(
        (int(W * 0.81), 0),
        (int(W * 0.86), int(H * 0.07)),
        (int(W * 0.94), int(H * 0.16)),
        (int(W * 0.99), int(H * 0.27)),
    )
    b_sec_tr_right.reverse()
    draw.polygon(b_sec_tr_left + b_sec_tr_right, fill=c_sec)

    # 2. Bottom-Left Waves
    # Primary wave
    b_pri_bl = bezier_curve(
        (0, int(H * 0.76)),
        (int(W * 0.10), int(H * 0.85)),
        (int(W * 0.18), int(H * 0.93)),
        (int(W * 0.25), H),
    )
    draw.polygon([(0, int(H * 0.76))] + b_pri_bl + [(0, H)], fill=c_pri)

    # Secondary ribbon
    b_sec_bl_outer = bezier_curve(
        (0, int(H * 0.58)),
        (int(W * 0.13), int(H * 0.74)),
        (int(W * 0.22), int(H * 0.87)),
        (int(W * 0.32), H),
    )
    b_sec_bl_inner = bezier_curve(
        (0, int(H * 0.70)),
        (int(W * 0.08), int(H * 0.82)),
        (int(W * 0.16), int(H * 0.92)),
        (int(W * 0.24), H),
    )
    b_sec_bl_inner.reverse()
    draw.polygon(
        b_sec_bl_outer + [(int(W * 0.24), H)] + b_sec_bl_inner + [(0, int(H * 0.58))],
        fill=c_sec,
    )

    # 3. Clean Inset Border Frame in Primary Color
    pad_x, pad_y = int(W * 0.035), int(H * 0.03)
    draw.rectangle([pad_x, pad_y, W - pad_x, H - pad_y], outline=c_pri, width=3)

    # 4. Corner Flourishes in Primary Color
    flourish_mask = os.path.join(
        settings.BASE_DIR, "static", "img", "corner_flourish_mask.png"
    )
    if os.path.exists(flourish_mask):
        try:
            mask = Image.open(flourish_mask)
            flourish = Image.new("RGBA", mask.size, c_pri)
            flourish.putalpha(mask)
            img.paste(flourish, (pad_x + 12, pad_y + 12), flourish)
            flourish_br = flourish.rotate(180)
            img.paste(
                flourish_br,
                (W - pad_x - flourish.width - 12, H - pad_y - flourish.height - 12),
                flourish_br,
            )
        except Exception:
            pass

    # Downsample to A4 (1240 x 1754) with Lanczos antialiasing
    res = img.resize((1240, 1754), Image.Resampling.LANCZOS).convert("RGB")
    res.save(out_path, optimize=True)

    # Also keep a copy in static for web display if available
    try:
        static_frames_dir = os.path.join(
            settings.BASE_DIR, "static", "img", "school_frames"
        )
        os.makedirs(static_frames_dir, exist_ok=True)
        static_copy = os.path.join(static_frames_dir, filename)
        if not os.path.exists(static_copy):
            res.save(static_copy, optimize=True)
    except Exception:
        pass

    return out_path
