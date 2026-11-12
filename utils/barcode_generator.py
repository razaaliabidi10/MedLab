import io
import re
import barcode
from barcode.writer import ImageWriter


def generate_barcode_png(barcode_string):
    """
    Generates a Code128 barcode image (PNG format) with high clarity
    suitable for clinical sample labeling, scanning, and downloading.
    """
    clean_code = re.sub(r'[^A-Za-z0-9\-_.]', '', str(barcode_string or '').strip())
    if not clean_code:
        clean_code = "000000"

    Code128 = barcode.get_barcode_class('code128')
    rv = io.BytesIO()
    bc = Code128(clean_code, writer=ImageWriter())
    bc.write(rv, options={
        'module_width': 0.35,
        'module_height': 16.0,
        'font_size': 11,
        'text_distance': 4.5,
        'quiet_zone': 3.0,
        'write_text': True
    })
    return rv.getvalue()

