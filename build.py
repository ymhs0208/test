"""Rebuild the offline competition prototype from the adjacent official workbooks."""

from argparse import ArgumentParser
from collections import defaultdict
from datetime import date
import json
import os
from pathlib import Path
from urllib.parse import quote

import numpy as np
from openpyxl import load_workbook


HERE = Path(__file__).resolve().parent
LOCAL_OUTPUT = HERE / "local-output"
KINDS = ("平時檢測", "定期檢測")
FEATURES = (
    "上次最高 D",
    "上次最高 E（已評等）",
    "上次最高 R（已評等）",
    "上次最高 U（已評等）",
    "上次記錄的劣化類型數",
    "近兩次最高 D 變化",
    "距上次同類檢測天數",
    "同類檢測紀錄次數",
    "檢測類型",
)


def read_rows(source, prefix):
    paths = sorted(source.glob(f"{prefix}.*.xlsx"))
    if len(paths) != 1:
        raise ValueError(f"Expected one source workbook starting with {prefix}.: {paths}")
    workbook = load_workbook(paths[0], read_only=True, data_only=True)
    try:
        reader = iter(workbook.active.values)
        header = next(reader)
        return [dict(zip(header, row)) for row in reader if row[0] is not None]
    finally:
        workbook.close()


def load_histories(source):
    bridges = {row["系統ID"]: row for row in read_rows(source, 1)}
    photo_folder, = (path for path in source.glob("3.*") if path.is_dir())
    photos = {path.stem: quote(os.path.relpath(path, LOCAL_OUTPUT))
              for path in photo_folder.glob("*.jpg")}
    joints = {}
    observations = defaultdict(dict)
    for row in read_rows(source, 3):
        joint = row["伸縮縫資料表ID"]
        bridge = bridges[row["基本資料系統ID"]]
        position = f'{row["構件位置"]} {row["構件編號"]}'
        metadata = {
            "name": row["橋梁名稱"],
            "position": position,
            "km": bridge["橋頭里程(K)"] + bridge["橋頭里程(M)"] / 1000,
        }
        if joints.setdefault(joint, metadata) != metadata:
            raise ValueError(f"Conflicting component metadata for {joint}")

        kind = row["檢測類型"]
        if kind not in KINDS:
            raise ValueError(f"Unexpected inspection type {kind}")
        day = row["檢測日期"].date()
        observation = observations[joint, kind].setdefault(day, [])
        observation.append({
            "defect": row["劣化類型"],
            "grades": [row[grade] for grade in "DERU"],
            "photos": [photos[name.strip()] for name in
                       (row["檢測照片編號"] or "").split(",") if name.strip()],
        })

    for key, by_date in observations.items():
        observations[key] = [
            {
                "date": day,
                "grades": [max((r["grades"][i] for r in records
                               if r["grades"][i] is not None), default=None)
                           for i in range(4)],
                "defects": sorted({r["defect"] for r in records if r["defect"]}),
                "rows": records,
            }
            for day, records in sorted(by_date.items())
        ]
    return joints, observations


def make_snapshot(observations, year):
    cutoff = date(year, 1, 1)
    stop = date(year + 1, 1, 1)
    candidates = []
    for (joint, kind), history in sorted(observations.items()):
        known = [item for item in history if item["date"] < cutoff]
        if not known:
            continue
        previous = known[-1]
        future = next((item for item in history if cutoff <= item["date"] < stop), None)
        d, e, r, u = previous["grades"]
        features = [
            d, e or 0, r or 0, u or 0, len(previous["defects"]),
            d - known[-2]["grades"][0] if len(known) > 1 else 0,
            (cutoff - previous["date"]).days, len(known), int(kind == "定期檢測"),
        ]
        target = None
        new_defects = []
        if future:
            new_defects = sorted(set(future["defects"]) - set(previous["defects"]))
            target = int(future["grades"][0] > d or bool(new_defects))
        candidates.append({
            "id": joint, "kind": kind, "features": features, "history": known,
            "future": future, "target": target, "new_defects": new_defects,
        })
    return candidates


def sigmoid(values):
    return 1 / (1 + np.exp(-np.clip(values, -40, 40)))


def fit_model(training):
    x = np.array([item["features"] for item in training], dtype=float)
    y = np.array([item["target"] for item in training], dtype=float)
    mean = x.mean(axis=0)
    scale = x.std(axis=0)
    scale[scale == 0] = 1
    design = np.column_stack([np.ones(len(x)), (x - mean) / scale])
    # Fixed L2 penalty with an unpenalized intercept.
    penalty = np.diag([0] + [1.0] * x.shape[1])
    beta = np.zeros(design.shape[1])
    for _ in range(50):
        probability = sigmoid(design @ beta)
        weights = probability * (1 - probability)
        hessian = (design.T * weights) @ design + penalty
        gradient = design.T @ (probability - y) + penalty @ beta
        step = np.linalg.solve(hessian, gradient)
        beta -= step
        if np.max(np.abs(step)) < 1e-9:
            return mean, scale, beta
    raise RuntimeError("Logistic regression did not converge")


def public_record(item, joint, model, identity):
    mean, scale, beta = model
    contribution = (np.array(item["features"]) - mean) / scale * beta[1:]
    reason_indices = np.flatnonzero(contribution > 0.025)
    ordered_reasons = sorted(reason_indices, key=lambda i: -contribution[i])[:3]
    last = item["history"][-1]
    displayed_values = list(item["features"])
    displayed_values[1:4] = [grade if grade is not None else "未評等" for grade in last["grades"][1:4]]
    displayed_values[-1] = item["kind"]
    return {
        **joint, "id": identity, "score": float(sigmoid(beta[0] + contribution.sum())),
        "d": last["grades"][0], "last": last["date"].isoformat(),
        "reasons": [{"label": FEATURES[i], "value": displayed_values[i]} for i in ordered_reasons],
        "history": item["history"], "future": item["future"],
        "newDefects": item["new_defects"], "target": item["target"],
    }


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Private local data directory")
    args = parser.parse_args()
    joints, observations = load_histories(args.source.resolve())
    training = [item for year in (2022, 2023, 2024)
                for item in make_snapshot(observations, year)
                if item["target"] is not None]
    test = make_snapshot(observations, 2025)
    assert all(item["future"]["date"].year < 2025 for item in training)
    assert all(len({item["id"] for item in test if item["kind"] == kind})
               == sum(item["kind"] == kind for item in test) for kind in KINDS)
    model = fit_model(training)
    payload = {"training": len(training), "byKind": {}}
    summary = {}
    for kind in KINDS:
        rows = [public_record(item, joints[item["id"]], model, item["id"])
                for item in test if item["kind"] == kind]
        rows.sort(key=lambda row: (-row["score"], row["last"], row["id"]))
        baseline = sorted(rows, key=lambda row: (-row["d"], row["last"], row["id"]))
        payload["byKind"][kind] = {"rows": rows, "baseline": [row["id"] for row in baseline]}
        summary[kind] = {
            "candidates": len(rows),
            "observed": sum(row["target"] is not None for row in rows),
            "positives": sum(row["target"] == 1 for row in rows),
            "counts": [
                [[sum(row["target"] == 1 for row in ordering[:k]),
                  sum(row["target"] is None for row in ordering[:k])]
                 for ordering in (rows, baseline)]
                for k in range(1, len(rows) + 1)
            ],
        }
        print(kind, {key: val for key, val in summary[kind].items() if key != "counts"},
              "top 10 [hits, unknown]", summary[kind]["counts"][9])

    def as_json(value):
        return json.dumps(value, ensure_ascii=False, default=date.isoformat).replace("<", "\\u003c")

    template = (HERE / "dashboard.template.html").read_text(encoding="utf-8")
    assert template.count("__SNAPSHOT__") == 1
    LOCAL_OUTPUT.mkdir(exist_ok=True)
    (LOCAL_OUTPUT / "index.html").write_text(template.replace("__SNAPSHOT__", as_json(payload)), encoding="utf-8")
    # The conversational view uses only aggregate counts, with no inspection rows or photos.
    if (HERE / "comparison.template.html").is_file():
        preview = LOCAL_OUTPUT / "backtest-preview.html"
        preview_template = (HERE / "comparison.template.html").read_text(encoding="utf-8")
        assert preview_template.count("__SUMMARY__") == 1
        preview.write_text(preview_template.replace("__SUMMARY__", as_json(summary)), encoding="utf-8")


if __name__ == "__main__":
    main()
