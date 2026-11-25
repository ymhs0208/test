# 伸縮縫巡檢排序原型

用歷次檢測資料排出優先巡檢清單，並在相同巡檢量下比較模型排序和依上次最高 D 評等排序的結果。

## 開啟示範

下載或 clone 儲存庫後，在瀏覽器開啟 `index.html`。可切換平時／定期檢測、巡檢量和排序方式，再點選構件查看排序原因、歷次評等和後續檢測。

公開頁面的橋梁、里程、檢測及回測結果均由 `demo.py` 模擬。照片欄位留空。若要重新產生示範頁：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python demo.py
```

## 使用已獲授權的本機資料

執行以下指令，將來源指向存有橋梁基本資料、檢測工作簿與檢測照片的原始資料夾：

```bash
python build.py --source "/path/to/authorized-data"
```

在瀏覽器開啟 `local-output/index.html`。頁面透過相對路徑讀取來源資料夾裡的照片。含原始檢測紀錄的本機成果放在 `local-output/`，Git 已設定忽略該目錄。

## 回測

模型使用年初以前可取得的檢測資料。它以同類檢測中出現新增劣化類型或最高 D 上升為命中。當年缺少同類檢測的候選項目列為未觀察。打開頁面底部的「回測方法與資料」可查看基準與訓練設計。

## 歷史照片比對與 AI 複核

從首頁選「照片複核」，或在瀏覽器直接開啟 `photo-review.html`。選擇構件與前後日期可比對照片，亦可切換「AI 優先」和「依日期瀏覽」，儲存複核結果及匯出找圖計時 CSV。公開頁使用獨立產生的合成示意圖和示範分數，可用 `python demo_photo.py` 重新產生。

有授權資料時，在裝有 Apple Vision 與 Swift 的 macOS 上執行：

```bash
python build.py --source "/path/to/authorized-data"
python build_photo_review.py --source "/path/to/authorized-data"
```

開啟 `local-output/photo-review.html`。若另有逐張複核標記，可用 `--annotations` 指定 JSON，格式為照片檔名（省略副檔名）對應 `water`、`debris`、`damage`、`other`、`uncertain` 或 `diagram`。驗證僅採用按橋梁名稱分組後留出的照片。影像特徵快取與本機成果均已設定由 Git 忽略。

找圖比較時，先選好同一複核項目、搜尋範圍和目標，在任一排序下按「開始找圖計時」。找到後點選照片並按「確認找到」。正式試用可交替兩種排序以控制練習效應，並以匯出的照片 ID 核對是否成功。
