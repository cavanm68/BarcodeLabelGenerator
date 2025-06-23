from flask import Flask, request, send_file, render_template_string
from flask import send_from_directory
from generator import generate_labels
from generator import parse_sku_list
import re
import tempfile


app = Flask(__name__)

@app.route('/previews/<path:filename>')
def serve_previews(filename):
    return send_from_directory('previews', filename)

@app.route("/")
def index():
    try:
        with open("index.html", encoding="utf-8") as f:
            return render_template_string(f.read())
    except FileNotFoundError:
        return "<h1>Error: index.html not found</h1>", 500


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()

    barcode_type = data.get("barcode_type", "code128")
    quantity = int(data.get("quantity", 1))
    rng_length = int(data.get("rng_length", 6))
    prefix = data.get("prefix", "")
    suffix = data.get("suffix", "")
    label_width = float(data.get("label_width", 4))
    label_height = float(data.get("label_height", 6))
    rows = int(data.get("rows", 1))
    columns = int(data.get("columns", 1))
    rng_charset = data.get("rng_charset", "digits")
    repeat_skus = data.get("repeat_skus", False)
    no_symbols = bool(data.get("no_symbols", False))
    layout_mode = data.get("layout_mode", "stacked")
    text_size = int(data.get("text_size", 14))
    barcode_size = int(data.get("barcode_size", 150))
    layout_reversed = bool(data.get("layout_reversed", False))
    dpi = int(data.get("dpi", 300))
    raw_skus = data.get("sku_list", "")
    if isinstance(raw_skus, list):
        sku_list = raw_skus
    else:
        sku_list = re.split(r"[,\s]+", raw_skus.strip())
        sku_list = [sku for sku in sku_list if sku]
    sku_list_raw = data.get("sku_list", "")
    use_manual_preview = parse_sku_list(sku_list_raw)
    x_offset = float(data.get("x_offset", 0))
    y_offset = float(data.get("y_offset", 0))
    truncate_templates = data.get("truncate_templates", [])

    use_manual_preview = data.get("use_manual_preview", False)
    if isinstance(use_manual_preview, str):
        use_manual_preview = use_manual_preview.lower() == "true"


    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        output_path = tmp_file.name

    generate_labels(
        barcode_type=barcode_type,
        quantity=quantity,
        rng_length=rng_length,
        prefix=prefix,
        suffix=suffix,
        output_path=output_path,
        label_width=label_width,
        label_height=label_height,
        rows=rows,
        columns=columns,
        rng_charset=rng_charset,
        repeat_skus=repeat_skus,
        no_symbols=no_symbols,
        layout_mode=layout_mode,
        text_size=text_size,
        barcode_size=barcode_size,
        layout_reversed=layout_reversed,
        dpi=dpi,
        sku_list = sku_list,
        use_manual_preview=use_manual_preview,
        x_offset=x_offset,
        y_offset=y_offset,
        truncate_templates=truncate_templates
    )

    return send_file(output_path, as_attachment=True, download_name="labels.pdf")

from werkzeug.middleware.dispatcher import DispatcherMiddleware
from flask import Flask

flask_app = Flask(__name__)

application = DispatcherMiddleware(None, {
    '/extras/barcode-label-generator': flask_app
})
