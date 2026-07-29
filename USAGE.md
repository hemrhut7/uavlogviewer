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

# 載入特定日誌檔
python -u main.py data/2026-04-17\ 14-14-16.tlog
```

---

## 2. 核心功能簡介

1. **多格式日誌解析**：自動識別 MAVLink (`.tlog`, `.mavlink`)、DataFlash (`.bin`, `.log`) 與 DJI 飛行日誌。
2. **互動式多圖表顯示 (Multi-Chart)**：支援多頻道獨立勾選、繪製、時間軸同步 (X-axis Sync) 與游標同步。
3. **飛行模式與事件標記**：自動根據日誌中的 `MODE` 數據繪製高對比度飛行模式背景區間。
4. **參數檢視 (Param Viewer)** 與 **數值計算 (Expression Editor / Data Calculator)**。

---

*祝您分析愉快！*
