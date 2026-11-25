"""Rebuild the public demonstration using independently simulated records."""

from datetime import date
import json
from random import Random

from build import HERE, KINDS, fit_model, make_snapshot, public_record

DEFECTS = ("示範漏水", "示範雜物堆積", "示範裝置損傷")


def simulate():
    rng = Random(3801)
    joints = {}
    observations = {}
    for component in range(1, 81):
        joints[component] = {
            "name": f"示範橋梁 {(component + 3) // 4:02d}",
            "position": f"橋台 A{1 + ((component - 1) % 4)}",
            "km": round(1 + component * 0.35, 3),
        }
        susceptibility = rng.random()
        for kind in KINDS:
            history = []
            for year in range(2021, 2026):
                if year != 2021 and rng.random() < 0.12:
                    continue
                count = (1 if kind == KINDS[1] else rng.choice((1, 2)))
                for month in (4, 9)[:count]:
                    defects = sorted(
                        defect for index, defect in enumerate(DEFECTS)
                        if rng.random() < 0.12 + susceptibility * 0.48 - index * 0.05
                    )
                    scores = [2 + int(len(defects) == 3), 1 + len(defects), 2, 2] if defects else [1, None, None, None]
                    history.append({
                        "date": date(year, month, rng.randrange(1, 27)),
                        "grades": scores,
                        "defects": defects,
                        "rows": [{"defect": defect, "grades": scores, "photos": []}
                                 for defect in (defects or [None])],
                    })
            observations[component, kind] = history
    return joints, observations


def main():
    joints, observations = simulate()
    training = [
        item for year in (2022, 2023, 2024)
        for item in make_snapshot(observations, year)
        if item["target"] is not None
    ]
    model = fit_model(training)
    payload = {"training": len(training), "byKind": {}}
    test = make_snapshot(observations, 2025)
    for kind in KINDS:
        rows = [
            public_record(item, joints[item["id"]], model, item["id"])
            for item in test if item["kind"] == kind
        ]
        rows.sort(key=lambda row: (-row["score"], row["last"], row["id"]))
        baseline = sorted(rows, key=lambda row: (-row["d"], row["last"], row["id"]))
        payload["byKind"][kind] = {"rows": rows, "baseline": [row["id"] for row in baseline]}

    template = (HERE / "dashboard.template.html").read_text(encoding="utf-8")
    template = template.replace("國道 1 號 · 林口至新竹系統", "合成資料示範 · 非實際橋梁")
    template = template.replace(
        "來源為高公局競賽提供的橋梁基本資料、檢測紀錄和檢測照片。里程是橋頭所在里程。模型使用檢測歷程。",
        "橋梁、里程與檢測紀錄由 demo.py 模擬。這些結果用於展示操作流程。",
    )
    snapshot = json.dumps(payload, ensure_ascii=False, default=date.isoformat).replace("<", "\\u003c")
    (HERE / "index.html").write_text(template.replace("__SNAPSHOT__", snapshot), encoding="utf-8")


if __name__ == "__main__":
    main()
