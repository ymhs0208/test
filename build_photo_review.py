"""Build the offline photo comparison page from authorized inspection records."""

from argparse import ArgumentParser
from collections import defaultdict
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import quote

import numpy as np
from openpyxl import load_workbook
from PIL import Image


HERE = Path(__file__).resolve().parent
LABELS = {
    "漏水": "water",
    "伸縮縫間雜物堆積": "debris",
    "伸縮縫裝置損傷(變形、生銹、腐蝕)": "damage",
}
CLASSES = ("water", "debris", "damage", "other")
BRIDGE_DIRECTION = re.compile(r"[（(](北向|南向|南北向|東向|西向|雙向)[)）]")


def read_catalog(source, output):
    folder, = (p for p in source.glob("3.*") if p.is_dir())
    files = sorted(folder.glob("*.jpg"))
    number_by_stem = {path.stem: i for i, path in enumerate(files)}
    workbook_path, = source.glob("3.*.xlsx")
    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    joints = {}
    photos = [None] * len(files)
    try:
        records = iter(workbook.active.values)
        header = next(records)
        for cells in records:
            row = dict(zip(header, cells))
            joint = row["伸縮縫資料表ID"]
            bridge = row["橋梁名稱"]
            day = row["檢測日期"].date().isoformat()
            group = joints.setdefault(joint, {
                "id": joint, "bridge": bridge,
                "position": f'{row["構件位置"]} {row["構件編號"]}',
                "group": BRIDGE_DIRECTION.sub("", bridge).strip(),
                "dates": defaultdict(list),
            })
            for stem in (row["檢測照片編號"] or "").split(","):
                if not stem.strip():
                    continue
                index = number_by_stem[stem.strip()]
                if photos[index] is not None:
                    raise ValueError(f"Duplicate inspection photo reference: {stem}")
                photos[index] = {
                    "id": index, "file": stem.strip(),
                    "src": quote(os.path.relpath(files[index], output)),
                    "label": row["劣化類型"],
                    "grades": [row[grade] for grade in "DERU"],
                    "inspection": row["檢測類型"],
                    "joint": joint, "date": day,
                }
                group["dates"][day].append(index)
    finally:
        workbook.close()
    if any(photo is None for photo in photos):
        raise ValueError("At least one photo has no corresponding inspection record")
    return files, joints, photos


def is_reference_diagram(path):
    # The workbooks also reference location diagrams with a flat green background.
    with Image.open(path) as image:
        image.draft("RGB", (64, 64))
        pixels = np.asarray(image.convert("RGB").resize((64, 64)), dtype=np.int16)
    distance = np.max(np.abs(pixels - [187, 208, 151]), axis=2)
    return bool(np.mean(distance <= 13) > 0.25)


def file_signature(files):
    signatures = (f"{path}\t{path.stat().st_size}\t{path.stat().st_mtime_ns}" for path in files)
    return sha256("\n".join(signatures).encode()).hexdigest()


def load_features(files, cache):
    signature = file_signature(files)
    metadata = cache / "feature-source.json"
    binary = cache / "features.bin"
    manifest = cache / "manifest.tsv"
    desired = {"media": signature, "extractor": sha256((HERE / "photo_features.swift").read_bytes()).hexdigest()}
    if not (metadata.exists() and binary.exists() and json.loads(metadata.read_text()) == desired):
        executable = cache / "photo-features"
        manifest.write_text("\n".join(map(str, files)) + "\n")
        subprocess.run(["swiftc", "-O", str(HERE / "photo_features.swift"), "-o", str(executable)], check=True)
        subprocess.run([str(executable), str(manifest), str(binary)], check=True)
        metadata.write_text(json.dumps(desired))
    features = np.fromfile(binary, dtype="<f4").reshape(len(files), -1)
    norms = np.linalg.norm(features, axis=1, keepdims=True)
    if not np.all(np.isfinite(features)) or np.any(norms <= 0):
        raise ValueError("Invalid image feature vectors")
    return features / norms


def is_heldout(bridge):
    return sha256(bridge.encode()).digest()[0] % 4 == 0


def rank_features(features, photos, joints):
    group_by_photo = np.array([joints[photo["joint"]]["group"] for photo in photos])
    heldout = np.array([is_heldout(group) for group in group_by_photo])
    diagrams = np.array([photo["diagram"] for photo in photos])
    test_vectors = {vector.tobytes() for vector in features[heldout & ~diagrams]}
    eligible = np.array([vector.tobytes() not in test_vectors for vector in features])
    train = ~heldout & ~diagrams & eligible
    categories = np.array([LABELS.get(photo["label"], "other") for photo in photos])
    x = np.asarray(features[train], dtype=np.float64)
    y = np.column_stack([categories[train] == label for label in CLASSES]).astype(float)
    counts = y.sum(axis=0)
    if not np.all(counts):
        raise ValueError("Each class requires at least one training photo")
    weights = (len(y) / (len(CLASSES) * counts))[y.argmax(axis=1)]
    design = np.column_stack([x, np.ones(len(x))])
    penalty = np.identity(design.shape[1])
    penalty[-1, -1] = 0
    model = np.linalg.solve((design.T * weights) @ design + penalty, (design.T * weights) @ y)
    prediction = np.column_stack([features, np.ones(len(features))]) @ model
    return prediction, heldout, train


def grade_proxy(photos, prediction, heldout, annotations):
    if not annotations:
        return None
    by_file = {photo["file"]: photo for photo in photos}
    totals = {label: {"n": 0, "model": 0, "record": 0} for label in CLASSES}
    checked = set()
    adjudicated = []
    for stem, label in annotations.items():
        if label in ("diagram", "uncertain"):
            continue
        photo = by_file[stem]
        index = photo["id"]
        if not heldout[index] or photo["diagram"] or label not in totals:
            raise ValueError(f"Invalid held-out review label: {stem}")
        checked.add(photo["joint"])
        adjudicated.append((photo, label))
        row = totals[label]
        row["n"] += 1
        row["model"] += int(CLASSES[prediction[index].argmax()] == label)
        row["record"] += int(LABELS.get(photo["label"], "other") == label)
    limit = min(5, len(adjudicated))
    chronological = sorted(adjudicated, key=lambda item: (item[0]["date"], -item[0]["id"]), reverse=True)
    for index, label in enumerate(CLASSES[:3]):
        ranked = sorted(chronological, key=lambda item: prediction[item[0]["id"], index], reverse=True)
        totals[label]["topAI"] = sum(mark == label for _, mark in ranked[:limit])
        totals[label]["topDate"] = sum(mark == label for _, mark in chronological[:limit])
    return {"classes": totals, "sampled": len(annotations), "joints": len(checked), "topLimit": limit}


def pair_photos(joint, photos, features):
    by_date = joint["dates"]
    dated = [(day, [i for i in ids if not photos[i]["diagram"]])
             for day, ids in sorted(by_date.items())]
    for later_index, (_, later) in enumerate(dated):
        if not later:
            continue
        for earlier_day, earlier in dated[:later_index]:
            if not earlier:
                continue
            matches = (features[later] @ features[earlier].T).argmax(axis=1)
            for index, match in zip(later, matches):
                photos[index].setdefault("matches", {})[earlier_day] = earlier[int(match)]


def render(payload, output):
    template = (HERE / "photo_review.template.html").read_text(encoding="utf-8")
    snapshot = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    output.mkdir(parents=True, exist_ok=True)
    (output / "photo-review.html").write_text(template.replace("__PHOTO_REVIEW__", snapshot), encoding="utf-8")


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=HERE.parent)
    parser.add_argument("--output-dir", type=Path, default=HERE / "local-output")
    parser.add_argument("--cache-dir", type=Path, default=HERE / ".photo-review-local")
    parser.add_argument("--annotations", type=Path)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    cache = args.cache_dir.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    files, joints, photos = read_catalog(args.source.resolve(), output)
    features = load_features(files, cache)
    for path, photo in zip(files, photos):
        photo["diagram"] = is_reference_diagram(path)
    prediction, heldout, train = rank_features(features, photos, joints)
    for photo, scores in zip(photos, prediction):
        photo["scores"] = None if photo["diagram"] else np.round(scores[:3], 5).tolist()
        photo["suggestion"] = None if photo["diagram"] else CLASSES[scores.argmax()]
    for joint in joints.values():
        pair_photos(joint, photos, features)
    annotations = json.loads(args.annotations.read_text()) if args.annotations else None
    validation = grade_proxy(photos, prediction, heldout, annotations)
    if validation:
        by_file = {photo["file"]: photo for photo in photos}
        groups = {joints[by_file[stem]["joint"]]["group"] for stem, mark in annotations.items()
                  if mark not in ("diagram", "uncertain")}
        validation["bridges"] = len(groups)
    data = {
        "sample": False, "photos": photos,
        "joints": sorted(joints.values(), key=lambda joint: (joint["bridge"], joint["position"])),
        "stats": {
            "train": int(train.sum()), "heldoutBridges": len({joint["group"] for joint in joints.values()
                                                            if is_heldout(joint["group"])}),
            "diagrams": sum(photo["diagram"] for photo in photos),
            "validated": validation,
        },
    }
    render(data, output)
    print(json.dumps(data["stats"], ensure_ascii=False))


if __name__ == "__main__":
    main()
