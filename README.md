# cut-video

自動偵測並剪掉影片中「結巴、重複說話、贅字口頭禪」的片段，讓你的影片更流暢。

## 它做了什麼？

1. **聽懂你說的話** — 用 AI 語音辨識，把影片中每個字和對應的時間都記錄下來
2. **找出該剪的地方** — 自動找到重複的詞（例如「我我我覺得」）、說到一半重來的句子、口頭禪贅字（「這個」「就是說」「嗯」「啊」），只保留有意義的內容
3. **強制移除敏感詞** — 可設定特定詞彙，不管在什麼語境都會被剪掉
4. **自動剪輯** — 把不要的片段剪掉，輸出乾淨的影片

## 費用

**語音辨識完全免費**，在你自己的電腦上執行，不需要帳號。

如果有設定 Gemini API Key，會額外使用 Google Gemini AI 來更精準地判斷哪些該剪（Gemini 有免費額度，一般使用不會收費）。沒有設定的話，會用本機的規則來分析，也能用。

---

## 流程

```
┌─────────────┐
│  輸入影片    │
│  input.mp4  │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────┐
│  Step 1. 語音辨識 (Whisper)  │  在本機執行，免費
│  產出每個字的文字＋時間戳       │
└──────┬──────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│  Step 2. 分析該剪的地方              │
│                                     │
│  有 Gemini API Key?                 │
│  ├─ 是 → 送 Gemini AI 分析          │
│  │        結巴＋贅字＋口頭禪＋敏感詞   │
│  │        （失敗時自動降級為本機規則）  │
│  └─ 否 → 本機規則分析                │
│           ├ 策略 1: 連續重複詞        │
│           ├ 策略 2: 說到一半重來      │
│           └ 策略 3: 多次嘗試取最長     │
│                                     │
│  + remove_words 強制移除（多詞拼接）   │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────────────────────┐
│  Step 3. 建立保留區間         │  合併相鄰的詞，產生時間段
└──────┬──────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│  Step 4. ffmpeg 剪輯                 │
│  ├ 依區間切出片段                     │
│  ├ 可選：奇數片段套用縮放（模擬雙機位） │
│  └ 串接所有片段                       │
└──────┬──────────────────────────────┘
       │
       ▼
┌──────────────┐
│  輸出影片     │
│  _clean.mp4  │
└──────────────┘
```

> 每次執行後都會自動輸出逐字稿 JSON，可手動修改 `keep` 欄位後用 `--from-transcript` 重新從 Step 3 開始剪輯（跳過語音辨識和分析）。

---

## 安裝（只需要做一次）

### macOS

打開「終端機」（Terminal），依序輸入以下指令：

```bash
# 第一步：安裝 ffmpeg（影片處理工具）
brew install ffmpeg

# 第二步：進入專案資料夾，建立環境
cd cut-video
python3 -m venv venv
source venv/bin/activate
pip install faster-whisper google-genai
```

### Windows

#### 第一步：安裝 Python

1. 前往 https://www.python.org/downloads/ 下載 Python（建議 **3.10 或 3.11** 版本）
2. 執行安裝程式，**務必勾選「Add Python to PATH」**（很重要！）
3. 安裝完成後，打開「命令提示字元」輸入 `python --version`，有顯示版本號就代表成功

#### 第二步：安裝 ffmpeg（影片處理工具）

1. 前往 https://www.gyan.dev/ffmpeg/builds/ 下載 `ffmpeg-release-essentials.zip`
2. 解壓縮到你喜歡的位置（例如 `C:\ffmpeg`）
3. 把裡面的 `bin` 資料夾路徑（例如 `C:\ffmpeg\bin`）加到系統的 PATH 環境變數
   - 不知道怎麼加？搜尋「Windows 設定環境變數 PATH」就有教學
4. 打開**新的**命令提示字元，輸入 `ffmpeg -version`，有顯示版本號就代表成功

#### 第三步：建立環境

打開「命令提示字元」，依序輸入：

```cmd
cd cut-video
python -m venv venv
venv\Scripts\activate
pip install faster-whisper google-genai
```

---

## 設定（config.json）

專案資料夾裡有一個 `config.json`，可以調整設定：

```json
{
  "gemini_api_key": "你的 Gemini API Key",
  "remove_words": ["不想出現的詞A", "不想出現的詞B"]
}
```

| 設定 | 說明 |
|------|------|
| `gemini_api_key` | Google Gemini 的 API Key。有填就會自動使用 Gemini 來分析（更精準）；留空或不填就用本機規則分析 |
| `remove_words` | 要強制移除的詞彙清單。支援多詞拼接：例如語音辨識把「民辦教師」拆成「民」「辦」「教」「師」四個詞，只要拼起來匹配就會整組移除 |

### remove_words 用法

Whisper 語音辨識有時候會把一個詞拆成多個字，例如：

```
"名" + "辦" + "教" + "師"  →  拼接後 = "名辦教師"
```

如果你在 `remove_words` 裡放了 `"名辦教師"`，程式會自動把這四個連續的字一起移除。

建議同時放入可能的辨識變體：

```json
"remove_words": ["民辦教師", "名辦教師"]
```

### 如何取得 Gemini API Key？

1. 前往 https://aistudio.google.com/apikey
2. 登入 Google 帳號，點「Create API Key」
3. 複製產生的 Key，貼到 `config.json` 的 `gemini_api_key` 欄位

> Gemini 有免費額度，一般剪影片的使用量不會超過。如果沒有 API Key 也沒關係，程式會自動改用本機的規則來分析。

---

## 使用方式

每次使用前，先進入專案資料夾並啟動環境：

**macOS：**
```bash
cd cut-video
source venv/bin/activate
```

**Windows：**
```cmd
cd cut-video
venv\Scripts\activate
```

然後就可以開始剪輯（以下指令 macOS 和 Windows 都一樣）：

```bash
# 最簡單的用法 — 自動產出 input_clean.mp4
python cut_video.py input.mp4

# 自己指定輸出的檔名
python cut_video.py input.mp4 -o output.mp4

# 每次執行都會自動產出逐字稿 JSON（可用於手動微調，見下方說明）
```

> **提示：** 把 `input.mp4` 換成你自己的影片檔名就好。如果影片不在同一個資料夾，要用完整路徑，例如 `C:\Users\你的名字\Desktop\影片.mp4`。

---

## 手動微調剪輯

自動偵測不一定 100% 完美。如果你想自己決定哪些地方要剪、哪些要保留，可以這樣做：

**第一步：正常執行一次**

```bash
python cut_video.py input.mp4
```

執行後會自動產出一個 `.json` 檔案（例如 `input_clean.json`）。

**第二步：用文字編輯器打開 JSON 檔，手動修改**

檔案內容長這樣：

```json
[
  { "text": "大家好", "start": 0.5, "end": 0.98, "keep": true },
  { "text": "今天", "start": 2.8, "end": 3.1, "keep": false },
  { "text": "今天", "start": 3.5, "end": 3.8, "keep": true },
  { "text": "要", "start": 3.82, "end": 3.95, "keep": true }
]
```

每一行代表影片中的一個詞：
- `"keep": true` → 保留這個詞
- `"keep": false` → 剪掉這個詞

你只需要修改 `keep` 的值就好，其他欄位不要動。

**第三步：用修改後的 JSON 重新剪輯**

```bash
python cut_video.py input.mp4 --from-transcript input_clean.json
```

這次不會重跑語音辨識（很省時間），直接根據你的修改來剪輯。

---

## 參數一覽

| 參數 | 預設值 | 說明 |
|------|--------|------|
| `input` | （必填） | 你的影片檔案路徑 |
| `-o`, `--output` | 自動產生 `_clean` 檔名 | 指定輸出的檔名 |
| `--from-transcript` | — | 讀取修改過的逐字稿 JSON 來剪輯（跳過語音辨識） |

語音辨識使用 `medium` 模型（首次執行會自動下載約 1.5 GB）。

---

## 常見問題

**Q: 影片很長（超過 30 分鐘），會不會有問題？**

不會。語音辨識在本機跑，不受長度限制（只是會比較久）。Gemini 分析的部分，程式會自動把逐字稿分批送出，不用擔心超過上限。

**Q: 沒有設定 Gemini API Key 可以用嗎？**

可以。程式會自動改用本機的規則來分析結巴。Gemini 的判斷會更精準一些（特別是贅字和口頭禪），但本機規則也堪用。

**Q: Gemini 突然不能用了？**

程式會自動切換到本機規則繼續處理，不會中斷。常見原因和解法：
- **「API 金鑰無效」** → 檢查 config.json 裡的 key 有沒有打錯
- **「免費額度已用完」** → 等隔天額度重置，或先不設定 key 用本機規則
- **「網路連線失敗」** → 檢查網路連線

**Q: remove_words 沒有生效？**

Whisper 辨識出來的文字可能跟你預期的不同（例如「民」變成「名」）。建議查看自動產出的逐字稿 JSON，看看實際辨識出來的文字，再把對應的寫法加到 `remove_words` 裡。
