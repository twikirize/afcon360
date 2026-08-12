"""
QR code helper for AFCON360.

Generates inline (base64 data-URI) QR codes so they can be embedded directly
into HTML emails and web pages without needing a separate image endpoint or
an external image host. Used by the accommodation Booking Pass feature.
"""

import base64
import io

import qrcode


def qr_data_uri(data: str, box_size: int = 6, border: int = 4, error_correction: str = "M") -> str:
    """
    Render ``data`` (typically a booking pass URL) as a PNG QR code and return
    it as a base64 ``data:`` URI suitable for an ``<img src="...">`` attribute.

    Args:
        data: The string to encode (e.g. the absolute booking pass URL).
        box_size: Pixel size of each QR module.
        border: Quiet-zone border width in modules.
        error_correction: One of 'L', 'M', 'Q', 'H'.

    Returns:
        A ``data:image/png;base64,...`` string, or an empty string if QR
        generation fails for any reason (callers must handle the empty case).
    """
    if not data:
        return ""

    ec_map = {
        "L": qrcode.constants.ERROR_CORRECT_L,
        "M": qrcode.constants.ERROR_CORRECT_M,
        "Q": qrcode.constants.ERROR_CORRECT_Q,
        "H": qrcode.constants.ERROR_CORRECT_H,
    }
    ecc = ec_map.get(str(error_correction).upper(), qrcode.constants.ERROR_CORRECT_M)

    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=ecc,
            box_size=box_size,
            border=border,
        )
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except Exception:
        return ""
