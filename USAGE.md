# UAV Log Viewer 使用說明書 (Python PySide6 桌面版)

歡迎使用 UAV Log Viewer (Python PySide6 桌面版)。本軟體採用 PySide6 (Qt for Python)、PyMAVLink、NumPy 與 Plotly 提供高效能的 UAV 日誌（MAVLink `.tlog`、DataFlash `.bin`/`.log` 及 DJI 日誌）解析與視覺化分析功能。

## 1. 環境需求與啟動

### 1.1 需求環境
* **Python 3.9+**
* 依賴套件：`PySide6`, `plotly`, `pymavlink`, `numpy`, `pandas`, `matplotlib`

### 1.2 安裝依賴與啟動
在專案根目錄開啟終端機，執行以下指令：

```bash
# 安裝依賴
pip install -r requirements.txt

# 啟動應用程式
python -u main.py

# 載入特定日誌檔（單檔或多檔比較）
python -u main.py data/2026-04-17\ 14-14-16.tlog
python -u main.py flight1.bin flight2.bin
```

---

## 2. 核心功能簡介

1. **多格式日誌解析**：自動識別 MAVLink (`.tlog`, `.mavlink`)、DataFlash (`.bin`, `.log`) 與 DJI 飛行日誌。
2. **多日誌疊加比較 (Multi-Log Overlay Comparison)**：
   - 支援同時載入最多 8 個日誌檔案（拖放多檔、對話框多選或 CLI 多參數傳入）。
   - **時間軸自動歸零與位移微調**：載入多檔時自動以各檔案第一筆數據時間為基準進行時間軸歸零（t=0），並可為各檔案獨立微調時間位移（Offset, 秒）。
   - **多檔欄位疊加**：支援在同張圖表中疊加不同檔案的欄位，圖例自動標記檔案標籤（如 `[F1]`、`[F2]`）；支援欄位樹右鍵「一鍵加入所有檔案此欄位」以及 XY Scatter「為所有檔案複製此 pair」。
   - **飛行模式背景切換**：可選擇跟隨目前操作檔案或指定特定檔案之飛行模式色帶作為背景。
   - **參數差異比對 (Parameter Difference)**：一鍵比對多個日誌檔案間的所有機體參數，標示相異數值與缺失項目。
3. **互動式多圖表顯示 (Multi-Chart)**：支援多頻道獨立勾選、繪製、時間軸同步 (X-axis Sync) 與游標同步。
4. **飛行模式與事件標記**：自動根據日誌中的 `MODE` 數據繪製高對比度飛行模式背景區間。
5. **參數檢視 (Param Viewer)** 與 **數值計算 (Expression Editor / Data Calculator)**。
6. **繪圖區訊息匯出至 CSV (Export to CSV)**：將繪圖區中目前顯示的所有 Message / 數據欄位匯出為 `.csv` 檔案，多檔案比較模式下自動加上檔案前綴並對齊時間戳記。

---

*祝您分析愉快！*
