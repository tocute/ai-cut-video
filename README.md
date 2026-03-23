# cut-video

自動偵測並剪掉影片中「結巴、重複說話」的片段，讓你的影片更流暢。

## 它做了什麼？

1. **聽懂你說的話** — 用 AI 語音辨識，把影片中每個字和對應的時間都記錄下來
2. **找出結巴的地方** — 自動找到重複的詞（例如「我我我覺得」）或說到一半重來的句子，只保留最後一次完整的說法
3. **自動剪輯** — 把結巴的片段剪掉，並在剪接處加上輕微的畫面縮放，讓畫面切換更自然（模擬雙機位效果）

## 費用

**語音辨識完全免費**，在你自己的電腦上執行，不需要帳號。

如果有設定 Gemini API Key，會額外使用 Google Gemini AI 來更精準地判斷哪些是結巴（Gemini 有免費額度，一般使用不會收費）。沒有設定的話，會用本機的規則來分析，也能用。

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
  "zoom": 1.07
}
```

| 設定 | 說明 |
|------|------|
| `gemini_api_key` | Google Gemini 的 API Key。有填就會自動使用 Gemini 來分析結巴（更精準）；留空或不填就用本機規則分析 |
| `zoom` | 剪接處的畫面縮放比例。預設 `1.07`（放大 107%）。設成 `1.0` 可以關閉縮放效果 |

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

# 想要更精準的辨識（會比較慢）
python cut_video.py input.mp4 --model large-v3

# 順便產出逐字稿（用來手動微調，見下方說明）
python cut_video.py input.mp4 --transcript
```

> **提示：** 把 `input.mp4` 換成你自己的影片檔名就好。如果影片不在同一個資料夾，要用完整路徑，例如 `C:\Users\你的名字\Desktop\影片.mp4`。

---

## 手動微調剪輯

自動偵測不一定 100% 完美。如果你想自己決定哪些地方要剪、哪些要保留，可以這樣做：

**第一步：產出逐字稿**

```bash
python cut_video.py input.mp4 --transcript
```

這會產出一個 `.json` 檔案（例如 `input_clean.json`）。

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
| `--model` | `medium` | 語音辨識模型大小（見下方說明） |
| `--transcript` | 關閉 | 產出逐字稿 JSON，可用於手動微調 |
| `--from-transcript` | — | 讀取修改過的逐字稿 JSON 來剪輯 |

## 模型選擇

模型越大越精準，但速度越慢，首次使用會自動下載。

| 模型 | 速度 | 準確度 | 首次下載大小 |
|------|------|--------|-------------|
| `tiny` | 最快 | 低 | ~75 MB |
| `base` | 快 | 中低 | ~150 MB |
| `small` | 中等 | 中等 | ~500 MB |
| `medium` | 較慢 | 高 | ~1.5 GB |
| `large-v3` | 最慢 | 最高 | ~3 GB |

**建議：** 先用預設的 `medium`，如果覺得辨識不夠準確再換 `large-v3`。

---

## 縮放效果是什麼？

當結巴的片段被剪掉後，畫面會突然「跳一下」（這叫 Jump Cut）。為了讓觀眾看起來更自然，這個工具會在每個剪接處交替放大畫面：

```
片段 1 (正常) → 片段 2 (放大 107%) → 片段 3 (正常) → 片段 4 (放大 107%) → ...
```

這樣看起來就像是刻意的鏡頭切換，而不是突兀的跳剪。如果不想要這個效果，在 `config.json` 把 `zoom` 設成 `1.0` 就好。

---

## 常見問題

**Q: 影片很長（超過 30 分鐘），會不會有問題？**

不會。語音辨識在本機跑，不受長度限制（只是會比較久）。Gemini 分析的部分，程式會自動把逐字稿分批送出，不用擔心超過上限。

**Q: 沒有設定 Gemini API Key 可以用嗎？**

可以。程式會自動改用本機的規則來分析結巴。Gemini 的判斷會更精準一些，但本機規則也堪用。

**Q: Gemini 突然不能用了？**

程式會自動切換到本機規則繼續處理，不會中斷。常見原因和解法：
- **「API 金鑰無效」** → 檢查 config.json 裡的 key 有沒有打錯
- **「免費額度已用完」** → 等隔天額度重置，或先不設定 key 用本機規則
- **「網路連線失敗」** → 檢查網路連線
