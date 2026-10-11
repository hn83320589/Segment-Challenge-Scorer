# Segment Challenge Scorer｜跑團區段挑戰計分工具

[![CI](https://github.com/hn83320589/Segment-Challenge-Scorer/actions/workflows/ci.yml/badge.svg)](https://github.com/hn83320589/Segment-Challenge-Scorer/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

匯入成員上傳的 GPX，自動比對挑戰區段，產生每月排行榜與跑者報告。這是命令列工具，成績全部由程式依同一套規則計算，幹部不必再手動在 Excel 對成績。

## 安裝與執行

需要 Python 3.12 以上與 [uv](https://docs.astral.sh/uv/)（macOS 可用 `brew install uv` 安裝）。

```bash
git clone https://github.com/hn83320589/Segment-Challenge-Scorer.git
cd Segment-Challenge-Scorer
uv sync                      # 依 uv.lock 安裝鎖定版本的相依套件
```

沒有 uv 也可以用 pip（不會套用 `uv.lock` 的鎖定版本，之後的指令把 `uv run` 拿掉即可）：

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e . pytest
scorer --help
```

用範例資料跑一次完整流程：

```bash
uv run scorer import sample_data/gpx
uv run scorer leaderboard RIVER-1K2 --config sample_data/segments.yaml --csv river.csv
uv run scorer report yuting --config sample_data/segments.yaml
```

執行測試：

```bash
uv run pytest
```

範例資料已放在 repo 中，也可以重新產生（輸出固定，結果與 repo 內的檔案逐位元組相同）：

```bash
uv run python scripts/generate_sample_data.py   # 輸出到 sample_data/
```

## 指令一覽

| 指令 | 說明 |
| --- | --- |
| `scorer import <資料夾>` | 匯入資料夾內所有 `.gpx`（不含子資料夾）。內容重複的檔案會略過（改名也一樣）。 |
| `scorer leaderboard <區段代碼> [--csv 路徑]` | 在終端機輸出排行榜；加上 `--csv` 時另存 CSV（UTF-8 BOM，Excel 可直接開啟）。 |
| `scorer report <runner_id>` | 列出該跑者每個活動的所有嘗試，包含有效成績、無效原因與剔除點數。 |

共用選項：

| 選項 | 環境變數 | 預設值 | 用於 |
| --- | --- | --- | --- |
| `--db PATH` | `SCORER_DB` | `scorer.db` | 全部指令 |
| `--config PATH` | `SCORER_CONFIG` | `segments.yaml` | `leaderboard`、`report` |

結束碼：

| 結束碼 | 意義 |
| --- | --- |
| 0 | 全部成功 |
| 2 | 匯入時有部分檔案失敗（其餘檔案仍會正常匯入，摘要會列出失敗的檔名與原因） |
| 1 | 參數或設定檔錯誤（訊息會指出出錯的欄位，例如 `segments[0].start.lat`） |

### 檔名規則

`<runner_id>_<任意>.gpx`，`runner_id` 是第一個底線之前的英數字，例如 `kevin_2026-10-03.gpx` 的跑者是 `kevin`。

## 區段設定檔

```yaml
segments:
  - code: RIVER-1K2              # 區段代碼（不可重複）
    name: 河堤直線 1.2K
    start: {lat: 25.0215000, lon: 121.5095000}
    end:   {lat: 25.0322918, lon: 121.5095000}
    radius_m: 25                 # 判定半徑（公尺），可省略，預設 25
    reference_length_m: 1200     # 參考長度（公尺）
    month: "2026-10"             # 挑戰月份 YYYY-MM（請加引號）
```

同一份檔案可以定義多個區段，完整範例見 [`sample_data/segments.yaml`](sample_data/segments.yaml)。

載入時除了檢查欄位格式，也會檢查幾何上是否合理，不合理時結束碼為 1，並指出欄位：

- 起點與終點的判定圈不可重疊（起終點距離必須大於 2 × 判定半徑）。
- 起終點直線距離不可超過參考長度 +10%。超過時，任何嘗試都不可能有效。

## 處理流程與演算法

### 1. 匯入與去重

- 每個 GPX 是一個活動。檔內有多個 track 或 segment 時，依各段第一個時間戳排序後合併。
- 用檔案內容的 SHA-256 判斷是否重複，與檔名無關。改名後重匯時，摘要會列出它與哪個已匯入的檔案相同；若 runner_id 也不同，會提醒「請確認是否上傳錯檔」。
- 時間一律視為 UTC，不帶時區標記的時間也視為 UTC。

### 2. 資料清理

依序檢查每個軌跡點：

1. 沒有時間戳：剔除，計入「無時間戳」。
2. 與**前一個保留點**推算的速度超過 30 km/h：視為 GPS 飄移剔除，計入「飄移」。時間沒有往前走（重複或倒退）的點無法推算速度，也一併剔除。

比對基準是「前一個保留點」，不是「前一個原始點」。所以一個飄移點不會連帶讓後面正常的點也被剔除。

**軌跡開頭的例外**：手錶剛定位完成時，頭幾個點常偏移數十到上百公尺。若照上面的規則，飄移的第一個點會成為基準，把後面一整串正常點都剔除。所以在保留點還少於 5 個時，只要之後連續 5 個點彼此一致、卻都被判為過快，就改判開頭保留的點才是飄移並剔除它們。軌跡中段不套用這個例外，避免持續好幾點的飄移反過來取代正常軌跡。

每個活動的兩種剔除數量都存在資料庫，`report` 會列出來。

### 3. 區段比對

對每個活動、每個區段，沿著清理後的軌跡跑一個簡單狀態機：

```
              進入起點圈                進入終點圈
  [等待起點] ───────────→ [計時中] ───────────→ 產生一次嘗試 → 回到 [等待起點]
                            │  ↺ 再次進入起點圈：以最後一次進入重新計時
                            └─ 軌跡結束仍未進入終點圈 → 無效「進入起點後未到終點」
```

- **進入**：前一點在圈外、這一點在圈內（以 haversine 距離 ≤ 判定半徑判斷，不考慮海拔）。軌跡第一個點就在圈內也算進入。取樣稀疏時，兩個點可能都在圈外，但連線穿過判定圈，這種情況也算進入。例如 10 秒取樣、離圓心 22 m 側向通過時，圈內的弦長只有約 24 m，可能沒有任何取樣點落在圈內。
- **邊界內插**：GPS 通常每 1–5 秒取樣一次，直接取取樣點時間會有好幾秒誤差。程式在進圈那一步的線段上，解出與判定圈邊界的第一個交點（以圓心為原點的局部平面座標解二次方程式），並依比例內插時間與位置。在測試中，即使 5 秒或 10 秒取樣，誤差也小於 0.01 秒。
- **內插的時間差上限**：相鄰兩點相隔超過 10 秒時，其中一點可能是飄移點，內插結果不可信，所以不內插。若已在圈內，就直接用圈內點的時間；若兩點都在圈外，則不認定為進圈。
- **成績**：從進入起點圈到進入終點圈的秒數，四捨五入到整數秒（0.5 秒進位）。起訖兩端都以「進圈」為準，所以量到的長度約等於起終點座標之間的距離。
- **多圈**：每完成一次嘗試就回到等待狀態，跑三圈就會有三次嘗試。
- **距離檢查**：實際距離是「起點交點 → 期間所有保留點 → 終點交點」相鄰距離的總和。若不在參考長度 ±10% 內，判為無效並記錄原因，例如「距離不符：實際 1434 m，參考 1200 m（容許 1080–1320 m）」。
- **反方向**：先經過終點才經過起點的軌跡不會產生有效嘗試。

成績在查詢時才計算，資料庫只存清理後的軌跡點。所以修改 `segments.yaml`（例如微調座標）後不必重新匯入，排行會直接反映新設定。

### 4. 月份歸屬

活動依**第一個保留點**的 Asia/Taipei 當地日期歸屬月份。例如 UTC `2026-09-30T16:30:00Z` 是台北時間 10/1 00:30，歸屬 `2026-10`。只有歸屬月份等於區段挑戰月份的嘗試才列入該區段排行；其他月份的有效嘗試仍會出現在 `report`，並標示「不列入排行」。

### 5. 排行

- 只採計有效、且月份相符的嘗試。
- 每位跑者只取最佳成績（秒數最少；同秒取較早完成的那次）。
- 依秒數排序，同秒時**完成時間（進入終點圈的時間）較早者排前面**。

## 範例輸出

以下輸出由 repo 內的範例資料產生（`tests/test_sample_data.py` 會驗證這份排行）：

```text
$ uv run scorer import sample_data/gpx
匯入摘要
  新增活動：25
  重複略過：0
  失敗：0

$ uv run scorer import sample_data/broken; echo "exit=$?"
匯入摘要
  新增活動：1
  重複略過：0
  失敗：2
    - morning-run.gpx：檔名格式錯誤，應為 <runner_id>_<任意>.gpx，runner_id 只能是英數字
    - zoe_2026-10-19.gpx：GPX 格式錯誤：Error parsing XML: unclosed token: line 18, column 79
exit=2

$ uv run scorer leaderboard RIVER-1K2 --config sample_data/segments.yaml --csv river.csv
RIVER-1K2 河堤直線 1.2K｜2026-10｜參考長度 1200 m
  名次  跑者    成績      秒數  完成時間（台北）     活動檔案
------  ------  ------  ------  -------------------  ---------------------
     1  hao     4:32       272  2026-10-10 06:43:20  hao_2026-10-10.gpx
     2  mei     4:47       287  2026-10-04 06:55:36  mei_2026-10-04.gpx
     3  kevin   4:47       287  2026-10-17 06:35:38  kevin_2026-10-17.gpx
     4  jason   4:59       299  2026-10-18 06:06:33  jason_2026-10-18.gpx
     5  zoe     5:08       308  2026-10-12 06:57:26  zoe_2026-10-12.gpx
     6  yuting  5:15       315  2026-10-24 07:06:01  yuting_2026-10-24.gpx
     7  lin     5:35       335  2026-10-25 06:06:24  lin_2026-10-25.gpx

已輸出 CSV：river.csv
```

mei 和 kevin 都是 287 秒，mei 在 10/4 先完成，所以排在前面。

```text
$ uv run scorer report yuting --config sample_data/segments.yaml
跑者 yuting：共 4 個活動

■ yuting_2026-10-04.gpx｜開始 2026-10-04 07:00:00｜歸屬 2026-10｜保留 911 點，剔除無時間戳 0、飄移 0
區段       進入起點             成績    實際距離    結果
---------  -------------------  ------  ----------  ------------------------------------------------------------
RIVER-1K2  2026-10-04 07:00:46  6:22    1434 m      無效：距離不符：實際 1434 m，參考 1200 m（容許 1080–1320 m）
RIVER-1K2  2026-10-04 07:23:55  5:22    1206 m      有效
WEST-1K4   2026-10-04 07:12:25  6:11    1408 m      有效
WEST-1K4   2026-10-04 07:34:40  6:16    1408 m      有效
...
```

### 範例資料內容

`scripts/generate_sample_data.py` 模擬 5 公里河堤環狀路線，共 6 位跑者、25 個活動。其中刻意包含以下情境：

| 情境 | 檔案 |
| --- | --- |
| 一次跑 2–3 圈（多次嘗試） | 多數檔案 |
| GPS 飄移點與缺時間戳的點 | `jason_2026-10-03.gpx` |
| 區段中途折返，距離不符 | `yuting_2026-10-04.gpx`（第 1 圈） |
| 進入起點後未到終點 | `mei_2026-10-18.gpx` |
| UTC `2026-09-30T16:30Z` 開始，歸屬 10 月 | `hao_2026-10-01.gpx` |
| 9 月活動，不列入 10 月排行 | `lin_2026-09-27.gpx` |
| 檔內有兩個 track | `hao_2026-10-10.gpx` |
| 同秒成績 | mei 與 kevin（287 秒） |
| 損毀檔、檔名錯誤 | `sample_data/broken/` |

## 專案結構

```
src/scorer/
  cli.py        Typer 指令與結束碼
  config.py     區段設定檔讀取與驗證
  track.py      GPX 解析、軌跡點清理
  matching.py   區段比對（狀態機 + 邊界內插）
  scoring.py    排行榜、跑者報告、CSV
  importer.py   批次匯入與去重
  db.py         SQLite schema migration 與存取
  geo.py        haversine、Asia/Taipei 月份歸屬
scripts/generate_sample_data.py
sample_data/    範例 GPX 與 segments.yaml
tests/          pytest
```

資料庫 schema 版本記錄在 SQLite 的 `PRAGMA user_version`。連線時會依序補跑 `db.MIGRATIONS` 中尚未套用的 migration。每個 migration 與版本號的更新在同一個交易內，中途失敗會整個撤銷。要修改 schema 時，只能在清單尾端新增。

## 已知限制

- 軌跡中段若連續好幾點都飄到同一個錯誤位置，跳回正常位置後，要等到某個點與最後保留點的推算速度回到 30 km/h 以下，才會恢復保留。這段期間的正常點也會被剔除。
- 計時從**進入**起點圈開始。在圈內原地等待的時間會算進成績。
- 在計時中又重新進入起點圈（例如在起點附近折返）會重新計時，前一段不另外記錄。
- 不處理同一位跑者使用多個 runner_id 的情況。
