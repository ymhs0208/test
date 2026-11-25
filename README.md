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
