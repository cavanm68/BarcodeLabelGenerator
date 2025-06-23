from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase import pdfmetrics
from PIL import Image
from pystrich.datamatrix import DataMatrixEncoder

import treepoem
import random
import string
import qrcode
import re

zint_map = {
    "code39": 1,
    "upce": 9,
    "interleaved2of5": 6,
    "datamatrix": 50,
    "ean13": 13,
    "ean8": 14,
    "upca": 34,
    }


SCALE_HEIGHT_BARCODES = {
    "interleaved2of5", 
    "code39", 
    "upce", 
    "upca", 
    "ean13", 
    "ean8", 
    "code128"
    }



def get_charset_pool(charset, no_symbols=False):
    if charset == "digits":
        pool = "0123456789"
    elif charset == "hex":
        pool = "0123456789ABCDEF"
    elif charset == "code39":
        pool = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-. $/+%"
    elif charset == "base64":
        pool = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    elif charset == "ascii":
        full_ascii = ''.join(chr(i) for i in range(32, 127))
        unsafe_chars = set('<>:"/\\|?*\'[]{}()^&~')
        pool = ''.join(c for c in full_ascii if c not in unsafe_chars)
    else:
        pool = "0123456789"
    if no_symbols:
        pool = ''.join(c for c in pool if c.isalnum())
    return pool

def truncate_sku(sku: str, side_len: int) -> str:
    if side_len == 0 or len(sku) <= side_len * 2:
        return sku
    return f"{sku[:side_len]}...{sku[-side_len:]}"


def parse_sku_list(sku_raw) -> list[str]:
    if isinstance(sku_raw, list):
        # It's already a list of strings — clean each one
        return [sku.strip() for sku in sku_raw if sku.strip()]
    elif isinstance(sku_raw, str):
        # Original logic: handle a raw string with commas/spaces/newlines
        tokens = re.split(r'[,\s]+', sku_raw.strip())
        return [sku for sku in tokens if sku]
    else:
        # In case something unexpected is passed
        return []


def generate_labels(
    barcode_type: str,
    quantity: int,
    rng_length: int,
    prefix: str = "",
    suffix: str = "",
    output_path: str = "output.pdf",
    label_width: float = 4,
    label_height: float = 6,
    rows: int = 1,
    columns: int = 1,
    rng_charset: str = "digits",
    repeat_skus: bool = False,
    no_symbols: bool = False,
    layout_mode: str = "stacked",
    text_size: float = 14,
    barcode_size: float = 150,
    layout_reversed: bool = False,
    dpi: int = 300,
    sku_list = None,
    use_manual_preview: bool = False,
    x_offset: int = 0,
    y_offset: int = 0,
    truncate_templates: list[int] = None,
):


    OUTPUT_SCALE_CORRECTION = 0.92  



    page_width = label_width * inch
    page_height = label_height * inch
    c = canvas.Canvas(output_path, pagesize=(page_width, page_height))

    def should_scale_barcode_height(barcode_type: str) -> bool:
        return barcode_type in SCALE_HEIGHT_BARCODES

    
    def is_valid_barcode(sku: str, barcode_type: str) -> bool:
        if barcode_type == "ean13":
            return sku.isdigit() and len(sku) == 12  # 12 digits + checksum is auto-added
        if barcode_type == "ean8":
            return sku.isdigit() and len(sku) == 7   # 7 digits + checksum
        if barcode_type == "upca":
            return sku.isdigit() and len(sku) == 11
        if barcode_type == "upce":
            return sku.isdigit() and len(sku) == 7
        return True


    def draw_barcode(sku, barcode_type, dpi):
        if barcode_type == "none":
            return None

        if barcode_type == "qrcode":
           return qrcode.make(sku).get_image().convert("RGB")

        if barcode_type == "code128":
            return treepoem.generate_barcode(barcode_type="code128", data=sku).convert("1")

        if barcode_type == "ean13":
            return treepoem.generate_barcode(barcode_type="ean13", data=sku).convert("1")

        if barcode_type == "ean8":
            return treepoem.generate_barcode(barcode_type="ean8", data=sku).convert("1")

        if barcode_type == "upca":
            return treepoem.generate_barcode(barcode_type="upca", data=sku).convert("1")


        if barcode_type in zint_map:
            return treepoem.generate_barcode(
                barcode_type=barcode_type,
                data=sku,
                options={"symbology": str(zint_map[barcode_type])},
            ).convert("1")

        if not is_valid_barcode(sku, barcode_type):
            raise ValueError(f"Invalid input '{sku}' for barcode type '{barcode_type}'")


        try:
            img = treepoem.generate_barcode(barcode_type=barcode_type, data=sku)
            return img.convert("RGB")
        except Exception as e:
            raise RuntimeError(f"Failed to generate barcode {barcode_type} for {sku}: {e}")

    

    def generate_scaled_qr(data, box_size=10, border=1):
        qr = qrcode.QRCode(
            version=None,  # automatically choose best fit
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=box_size,  # size of each box (in pixels)
            border=border  # white space around edges
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("1")
        return img

    def generate_scaled_datamatrix(data, scale=10):
        encoder = DataMatrixEncoder(data)
        encoder.save("temp_dm.png")  # Save barcode as a temporary image

        img = Image.open("temp_dm.png").convert("RGB")  # Read it as PIL image
        width, height = img.size
        img = img.resize((width * scale, height * scale), Image.NEAREST)
        return img

    def draw_stacked(x, y, cell_width, cell_height, sku, barcode_type, layout_reversed, text_size, suppress_text=False, display_text=None):
        nonlocal c
        spacing = 20
        effective_text_size = text_size * 1.5
        effective_barcode_size = barcode_size * 0.7
        adjustment = 62 if layout_reversed else 0

        if barcode_type in SCALE_HEIGHT_BARCODES:
            block_start_y = y + (cell_height - (effective_text_size + spacing + effective_barcode_size)) / 1.7 + adjustment
        else:
            block_start_y = y + (cell_height - (effective_text_size + spacing + effective_barcode_size)) / 2.1 + adjustment

        dynamic_shift = 0.025 * (rows ** 1.2 + columns ** 1.2)
        block_start_y -= dynamic_shift

        if barcode_type in ["qrcode", "datamatrix"]:
            if barcode_type == "qrcode":
                img = generate_scaled_qr(sku, box_size=10)
                base_pts = 1.7
            elif barcode_type == "datamatrix":
                img = generate_scaled_datamatrix(sku)
                base_pts = 1.6


            density_scale = min(1.0, 10 / (rows * columns) ** 0.45)  # more rows/cols  smaller content
            target_pts = barcode_size * base_pts * density_scale

            target_px = int(target_pts * dpi / 72)
            img = img.resize((target_px, target_px), Image.LANCZOS)
            img_reader = ImageReader(img)

            barcode_x = x + (cell_width - target_pts) / 2
            density_shift = 1.1 * (rows ** 1.25 + columns ** 1.25)
            barcode_y = y + (cell_height - target_pts) / 2.5 - density_shift

            if layout_reversed:
                barcode_y -= effective_text_size - 79 # this needs a better solution, but good for now

            spacing = 4
            if layout_reversed:
                text_y = barcode_y - effective_text_size - spacing
            else:
                text_y = barcode_y + target_pts + spacing

            c.drawImage(img_reader, barcode_x, barcode_y, width=target_pts, height=target_pts)

            if not suppress_text:
                c.setFont("Helvetica", effective_text_size)
                c.drawCentredString(x + cell_width / 2, text_y, display_text if display_text is not None else sku)



        else:
            barcode = draw_barcode(sku, barcode_type, dpi)
            if barcode:
                img_reader = ImageReader(barcode)

                is_grid = (rows * columns) > 1
                density_factor = (rows * columns) ** 0.45 if is_grid else 1

                if is_grid:
                    base_scale = 0.035  # Doubled for multi-label grids
                    height_scale = 0.012  # Slightly taller for visibility
                else:
                    base_scale = 0.0115  # Single-label size
                    height_scale = 0.0037

                draw_width = cell_width * base_scale * barcode_size
                shrink_factor = 1 + 0.0015 * (density_factor - 1)  # starts at 1, grows slowly
                draw_height = cell_height * height_scale * barcode_size / shrink_factor


                # Push the block downward slightly as density increases
                offset_factor = 2 + (density_factor * 0.35)
                offset_x = x + (cell_width - draw_width) / 2
                offset_y = y + (cell_height - draw_height) / offset_factor


                c.drawImage(
                    img_reader,
                    offset_x,
                    offset_y,
                    width=draw_width,
                    height=draw_height
                )

                # Draw the text label for 1D barcodes
                if not suppress_text:
                    text_y = offset_y + draw_height + 4 if not layout_reversed else offset_y - effective_text_size - 4
                    c.setFont("Helvetica", effective_text_size)
                    c.drawCentredString(x + cell_width / 2, text_y, display_text if display_text is not None else sku)


    def draw_side_by_side(x, y, cell_width, cell_height, sku, barcode_type, layout_reversed, text_size, display_text, barcode_size):
        spacing = 16
        effective_text_size = text_size * 1.4

        # Make barcode as big as possible in the cell
        max_barcode_width = cell_width * 0.55  
        max_barcode_height = cell_height * 0.95
        width_pts = min(barcode_size, max_barcode_width)
        height_pts = min(barcode_size, max_barcode_height)
        if should_scale_barcode_height(barcode_type):
            height_pts *= 0.2

        # Vertical centering
        center_y = y + cell_height / 2
        barcode_y = center_y - height_pts / 2

        # Compute maximum text width for wrapping
        max_text_width = max(cell_width * 0.45, cell_width - width_pts - 3 * spacing)
        max_text_height = height_pts
        max_chars_per_line = max(1, int(max_text_width / (effective_text_size * 0.6)))
        max_lines = 3

        def wrap_text(text, font_name, font_size, max_width, max_lines, truncate=False):
            lines = []
            current_line = ""
            for char in text:
                test_line = current_line + char
                if stringWidth(test_line, font_name, font_size) <= max_width:
                    current_line = test_line
                else:
                    lines.append(current_line)
                    current_line = char
                    if len(lines) >= max_lines - 1:
                        break
            if current_line:
                lines.append(current_line)
            if truncate and len(lines) == max_lines:
                final = lines[-1]
                while stringWidth(final + "...", font_name, font_size) > max_width and final:
                    final = final[:-1]
                lines[-1] = final + "..."
            return lines[:max_lines]

        truncate_enabled = False
        if isinstance(truncate_templates, list):
            truncate_enabled = True
        elif isinstance(truncate_templates, int):
            truncate_enabled = truncate_templates > 0


        def wrap_text_by_chars(text, max_chars_per_line, max_lines):
            lines = []
            for i in range(0, len(text), max_chars_per_line):
                if len(lines) >= max_lines:
                    break
                lines.append(text[i:i+max_chars_per_line])
            # Truncate last line with ellipsis if needed
            if len(lines) == max_lines and len(text) > max_lines * max_chars_per_line:
                last_line = lines[-1]
                lines[-1] = (last_line[:-3] + "...") if len(last_line) > 3 else "..."
            return lines

        wrapped_lines = wrap_text_by_chars(display_text, max_chars_per_line, max_lines)

        c.setFont("Helvetica", effective_text_size)
        total_text_height = len(wrapped_lines) * effective_text_size * 1.1
        start_y = center_y + total_text_height / 2 - effective_text_size

        if not layout_reversed:
            # Barcode on right, text on left
            barcode_x = x + cell_width - width_pts - spacing
            text_right = barcode_x - spacing  # right edge of text
            for i, line in enumerate(wrapped_lines):
                line_y = start_y - i * effective_text_size * 1.1
                text_width = stringWidth(line, "Helvetica", effective_text_size)
                c.drawString(text_right - text_width, line_y, line)
        else:
            # Barcode on left, text on right
            barcode_x = x + spacing
            text_left = barcode_x + width_pts + spacing  # left edge of text
            for i, line in enumerate(wrapped_lines):
                line_y = start_y - i * effective_text_size * 1.1
                c.drawString(text_left, line_y, line)

        # Draw the barcode image
        barcode = draw_barcode(sku, barcode_type, dpi)
        if barcode:
            img_reader = ImageReader(barcode)
            c.drawImage(
                img_reader,
                barcode_x,
                barcode_y,
                width=width_pts,
                height=height_pts
            )


    def draw_barcode_only(x, y, cell_width, cell_height, sku, barcode_type, barcode_size, include_debug_text=False):
        barcode = draw_barcode(sku, barcode_type, dpi)
        if barcode:
            img_reader = ImageReader(barcode)
            bt = barcode_type.lower()

            # 2D barcodes
            if bt == "qrcode":
                base_scale = 0.0085
                size = min(cell_width, cell_height) * base_scale * barcode_size
                draw_width = draw_height = size
            elif bt == "datamatrix":
                base_scale = 0.0055
                size = min(cell_width, cell_height) * base_scale * barcode_size
                draw_width = draw_height = size
            else:
                # 1D barcodes
                base_scale = 0.0065
                draw_width = cell_width * base_scale * barcode_size
                draw_height = cell_height * 0.002 * barcode_size  # Shorter height by default

            offset_x = x + (cell_width - draw_width) / 2
            offset_y = y + (cell_height - draw_height) / 2.3

            c.drawImage(
                img_reader,
                offset_x,
                offset_y,
                width=draw_width,
                height=draw_height
            )

            if include_debug_text:
                c.setFont("Helvetica", 1)
                c.setFillGray(0.8)
                c.drawCentredString(x + cell_width / 2, y + cell_height / 2, sku)


    def draw_text_only(x, y, cell_width, cell_height, display_text, text_size, layout_reversed, rows, columns, barcode_size):
        # Calculate max size allowed based on cell height
        max_text_size = cell_height * 0.5
        effective_text_size = min(text_size, max_text_size) * 1.5

        # Initial centered positions
        center_x = x + cell_width / 2
        center_y = y + cell_height / 2.2

        # Adjust text position based on label density
        shift = 0.35 * (rows ** 1.15 + columns ** 1.15)
        if layout_reversed:
            center_y -= shift
        else:
            center_y += shift

        # Draw text
        c.setFont("Helvetica-Bold", effective_text_size)
        c.drawCentredString(center_x, center_y, display_text)



    def draw_label_cell(x, y, cell_width, cell_height, sku, barcode_type, layout_mode, layout_reversed, text_size, display_text, rows, columns, barcode_size):
        layout = layout_mode.lower()
        if layout == "stacked":
            draw_stacked(x, y+20, cell_width, cell_height, sku, barcode_type, layout_reversed, text_size, display_text=display_text)
        elif layout == "side_by_side":
            draw_side_by_side(x, y, cell_width, cell_height, sku, barcode_type, layout_reversed, text_size, display_text, barcode_size)
        elif layout == "barcodeonly":
            draw_barcode_only(x, y, cell_width, cell_height, sku, barcode_type, barcode_size)
        elif layout == "textonly":
            draw_text_only(x, y, cell_width, cell_height, display_text, text_size, layout_reversed, rows, columns, barcode_size)


        else:
            raise ValueError(f"Unknown layout mode: {layout_mode}")

    def draw_grid(skus):
        cell_width = page_width / columns
        cell_height = page_height / rows
        labels_per_page = rows * columns

        for i in range(0, len(skus), labels_per_page):
            page_skus = skus[i:i + labels_per_page]
            index = 0
            for r in range(rows):
                for col in range(columns):
                    if index >= len(page_skus):
                        break
                    x = col * cell_width + x_offset
                    y = r * cell_height + y_offset - rows + columns
                    raw_sku = page_skus[index]
                    full_sku = f"{prefix}{raw_sku}{suffix}"
                    if layout_mode.lower() == "side_by_side":
                        display_text = f"{prefix}{raw_sku}{suffix}"
                    elif truncate_templates and index < len(truncate_templates):
                        trunc_len = truncate_templates[index]
                        display_text = truncate_sku(f"{prefix}{raw_sku}{suffix}", trunc_len)
                    else:
                        display_text = f"{prefix}{raw_sku}{suffix}"


                    draw_label_cell(
                        x, y,
                        cell_width, cell_height,
                        full_sku,  # always pass the full SKU for barcode
                        barcode_type, layout_mode, layout_reversed, text_size,
                        display_text,  # pass the truncated or full text for the label
                        rows, columns, barcode_size
                    )
                    index += 1
            c.showPage()




    def generate_rng_sku():
        if barcode_type == "upce":
            first = random.choice("01")
            rest = ''.join(random.choices(string.digits, k=rng_length - 1))
            return f"{first}{rest}"
        pool = get_charset_pool(rng_charset, no_symbols)
        core = ''.join(random.choices(pool, k=rng_length))
        return core

    label_count = quantity * rows * columns

    if use_manual_preview and sku_list:
        if len(sku_list) < label_count:
            if repeat_skus:
                times = (label_count + len(sku_list) - 1) // len(sku_list)
                sku_list = (sku_list * times)[:label_count]
            else:
                raise ValueError("Manual SKU list is shorter than label count and repeat_skus is false.")
        else:
            sku_list = sku_list[:label_count]




    labels_per_page = rows * columns
    total_labels = quantity * labels_per_page

    
    # manual
    if use_manual_preview and sku_list:
        if len(sku_list) < total_labels:
            if repeat_skus:
                times = (total_labels + len(sku_list) - 1) // len(sku_list)
                sku_list = (sku_list * times)[:total_labels]
            else:
                raise ValueError("Manual SKU list is shorter than label count and repeat_skus is false.")
        else:
            sku_list = sku_list[:total_labels]

        draw_grid(sku_list)

    # rng
    else:
        sku_list = [generate_rng_sku() for _ in range(total_labels)]
        draw_grid(sku_list)

    c.save()
    return output_path
