"""Create a public photo-review demo using illustrated fixtures and sample scores."""

from base64 import b64encode
from io import BytesIO
from random import Random

from PIL import Image, ImageDraw

from build_photo_review import CLASSES, HERE, render


LABELS = dict(zip(CLASSES, ("示範漏水", "示範雜物堆積", "示範裝置損傷", None)))
DAYS = ("2022-04-11", "2023-05-23", "2024-06-07", "2025-07-12")


def illustrate(seed, angle, label):
    rng = Random(seed)
    image = Image.new("RGB", (420, 235), "#50585a")
    draw = ImageDraw.Draw(image)
    if label == "water":
        draw.rectangle((0, 91, 419, 234), fill="#9e9b86")
        draw.polygon([(98, 86), (142, 86), (168, 227), (98, 227), (123, 134)], fill="#6b786a")
    else:
        for _ in range(620):
            x, y = rng.randrange(420), rng.randrange(235)
            draw.point((x, y), fill=rng.choice(("#40484a", "#697072", "#5b6264")))
        edges = [(150 + angle, 0), (176 + angle, 0), (274 - angle, 235), (186 - angle, 235)]
        draw.polygon(edges, fill="#aab0ac")
        draw.line([(162 + angle, 0), (230 - angle, 235)], fill="#242b30", width=7)
        if label == "debris":
            for step in range(23):
                y = 105 + (step * 5)
                x = int(162 + angle + (68 - 2 * angle) * y / 235) + rng.randrange(-6, 6)
                draw.ellipse((x - 3, y - 2, x + 3, y + 2), fill=rng.choice(("#a58d53", "#796e4b", "#c2a878")))
        if label == "damage":
            draw.line([(186, 99), (206, 127), (197, 160), (221, 186)], fill="#754a38", width=9)
            draw.polygon([(204, 123), (207, 158), (197, 169), (200, 137)], fill="#242b30")
    draw.rectangle((11, 11, 115, 36), fill="#243932")
    draw.text((19, 18), "DEMO ILLUSTRATION", fill="#e1eee5")
    out = BytesIO()
    image.save(out, format="JPEG", quality=71, optimize=True)
    return "data:image/jpeg;base64," + b64encode(out.getvalue()).decode("ascii")


def main():
    photos = []
    joints = []
    rng = Random(225)
    for joint_id in range(1, 5):
        dates = {}
        for date_index, day in enumerate(DAYS):
            dates[day] = []
            for angle in (0, 30):
                index = len(photos)
                label = CLASSES[(joint_id + date_index + (angle > 0)) % len(CLASSES)]
                scores = [round(rng.uniform(.05, .26) + (.58 if entry == label else 0), 3) for entry in CLASSES[:3]]
                matches = {earlier: ids[int(angle > 0)] for earlier, ids in dates.items() if earlier != day}
                photos.append({
                    "id": index, "file": f"DEMO-{index + 1:02d}", "src": illustrate(index, angle, label),
                    "label": LABELS[label], "grades": [1, None, None, None] if label == "other" else [2, 2, 2, 2],
                    "inspection": "示範檢測", "joint": joint_id, "date": day, "diagram": False,
                    "scores": scores, "suggestion": label, "matches": matches,
                })
                dates[day].append(index)
        joints.append({"id": joint_id, "bridge": f"示範橋梁 {joint_id:02d}", "position": "橋台 A1", "dates": dates})
    render({"sample": True, "photos": photos, "joints": joints, "stats": {"validated": None}}, HERE)


if __name__ == "__main__":
    main()
