import hashlib
import io
import textwrap

import numpy as np
from PIL import Image, ImageDraw

from scene_tracker.vision.masks import decode_mask


def png(image):
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def overlays(rgb, boxes, masks, tracks=None):
    boxes_image = rgb.copy()
    mask_image = rgb.copy()
    draw = ImageDraw.Draw(boxes_image)
    crops = []
    mask_index = {m.detection_id: m for m in masks}
    for box in boxes:
        mask = mask_index.get(box.id)
        color = tuple(70 + c % 140 for c in hashlib.sha256(box.fixture_id.encode()).digest()[:3])
        binary = (
            decode_mask(mask.rle).astype(bool)
            if mask
            else np.zeros((rgb.height, rgb.width), dtype=bool)
        )
        tinted = Image.new("RGB", rgb.size, color)
        blended = Image.blend(mask_image, tinted, 0.4)
        mask_image.paste(blended, mask=Image.fromarray(binary.astype(np.uint8) * 255))
        x1, y1, x2, y2 = box.box_xyxy
        draw.rectangle((x1, y1, x2 - 1, y2 - 1), outline=color, width=2)
        annotate(boxes_image, box, tracks)
        masked = Image.new("RGB", rgb.size, (127, 127, 127))
        masked.paste(rgb, mask=Image.fromarray(binary.astype(np.uint8) * 255))
        crops.append((box, (masked if mask else rgb).crop(box.box_xyxy)))
    for box in boxes:
        annotate(mask_image, box, tracks)
    sheet = Image.new("RGB", (320, max(1, (len(crops) + 1) // 2) * 140), "white")
    for index, (box, crop) in enumerate(crops):
        thumbnail = crop.copy()
        thumbnail.thumbnail((150, 110))
        position = (index % 2 * 160, index // 2 * 140)
        sheet.paste(thumbnail, position)
        ImageDraw.Draw(sheet).text(
            (position[0], position[1] + 112), f"{box.fixture_id} {box.label}", fill="black"
        )
    if not crops:
        ImageDraw.Draw(sheet).text((10, 10), "No fixture detections", fill="black")
    return boxes_image, mask_image, sheet, crops


def annotate(image, box, tracks=None):
    draw = ImageDraw.Draw(image)
    identifier = str(box.id)
    label = "\n".join(textwrap.wrap(box.label, width=22))
    track = (tracks or {}).get(str(box.id), "unassigned")
    track_label = "\n".join(textwrap.wrap(track, 20))
    text = (
        f"{identifier[:18]}\n{identifier[18:]}\n{label} score={box.score:.2f}\n"
        f"view-track: {track_label}\nphysical-object: unlinked"
    )
    bounds = draw.multiline_textbbox((0, 0), text, stroke_width=1)
    x = max(0, min(box.box_xyxy[0], image.width - bounds[2] - 2))
    y = max(0, min(box.box_xyxy[1], image.height - bounds[3] - 2))
    draw.multiline_text((x, y), text, fill="black", stroke_width=1, stroke_fill="white")
