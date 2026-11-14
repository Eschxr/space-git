"""Static, standalone inspection report and downloadable evidence bundle; no app/JS."""

import base64
import html
import io
import zipfile


def data_url(content_type, data):
    return f"data:{content_type};base64," + base64.b64encode(data).decode("ascii")


def report(run_id, cameras, files):
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'><title>Fake vision inspection</title>"
        "</head><body>",
        f"<h1>Synthetic fixture processing run {run_id}</h1>",
        "<p>FAKE adapters. No pretrained inference or model quality validation. "
        "No tracking, cross-view association or change proposals yet.</p>",
    ]
    for result in cameras:
        role = "OVERHEAD" if result.camera_id.value == "cam_04" else "side"
        parts.append(
            f"<section><h2>{result.camera_id.value} — {role}</h2>"
            f"<p>{html.escape(result.status)} {html.escape(result.error or '')}</p>"
        )
        for name in ("boxes.png", "masks.png", "crop_sheet.png"):
            path = f"debug/{result.camera_id}/{name}"
            if path in files:
                parts.append(
                    f"<figure><img alt='{name}' src='{data_url('image/png', files[path])}'>"
                    f"<figcaption>{name}</figcaption></figure>"
                )
        parts.append("</section>")
    parts.append("<h2>Evidence JSON</h2><ul>")
    for path, data in sorted(files.items()):
        if path.endswith(".json"):
            parts.append(
                f"<li><a download='{html.escape(path)}' "
                f"href='{data_url('application/json', data)}'>{html.escape(path)}</a></li>"
            )
    parts.append("</ul></body></html>")
    return "".join(parts).encode()


def bundle(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, data in sorted(files.items()):
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return stream.getvalue()
