#!/usr/bin/env python3
"""
自動偵測並剪掉影片中結巴、重複說話的片段。

使用方式:
    python cut_video.py input.mp4
    python cut_video.py input.mp4 -o output.mp4
    python cut_video.py input.mp4 --model large-v3
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

from faster_whisper import WhisperModel

SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config.json"


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def prefix_overlap(text_a: str, text_b: str) -> int:
    """Return the number of leading characters shared by two strings."""
    limit = min(len(text_a), len(text_b))
    for i in range(limit):
        if text_a[i] != text_b[i]:
            return i
    return limit


def get_video_info(video_path: str) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", video_path],
        capture_output=True, text=True,
    )
    info = json.loads(result.stdout)
    duration = float(info["format"]["duration"])
    width, height = 1920, 1080
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            width = int(stream["width"])
            height = int(stream["height"])
            break
    return {"duration": duration, "width": width, "height": height}


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------

def transcribe(video_path: str, model_size: str = "medium") -> list[dict]:
    print(f"[1/4] 載入語音辨識模型 ({model_size})...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    print("[2/4] 辨識語音中（這可能需要幾分鐘，請耐心等候）...")
    segments, _info = model.transcribe(
        video_path,
        language="zh",
        word_timestamps=True,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=300),
    )

    words = []
    for seg in segments:
        if seg.words:
            for w in seg.words:
                words.append({
                    "text": w.word.strip(),
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                })
        else:
            words.append({
                "text": seg.text.strip(),
                "start": round(seg.start, 3),
                "end": round(seg.end, 3),
            })

    print(f"   辨識到 {len(words)} 個詞")
    return words


# ---------------------------------------------------------------------------
# Stutter detection — rule-based (3 strategies)
# ---------------------------------------------------------------------------

def _detect_exact_repeats(words, keep, max_gap=3.0):
    """Strategy 1: consecutive identical phrases → keep last occurrence."""
    n = len(words)
    i = 0
    while i < n:
        best_len, best_count = 0, 0
        for plen in range(1, min(6, n - i)):
            phrase = [words[i + k]["text"] for k in range(plen)]
            count, j = 1, i + plen
            while j + plen <= n:
                candidate = [words[j + k]["text"] for k in range(plen)]
                gap = words[j]["start"] - words[j - 1]["end"]
                if candidate == phrase and gap < max_gap:
                    count += 1
                    j += plen
                else:
                    break
            if count > 1 and plen * count > best_len * best_count:
                best_len, best_count = plen, count

        if best_count > 1:
            for rep in range(best_count - 1):
                for k in range(best_len):
                    keep[i + rep * best_len + k] = False
            i += best_len * best_count
        else:
            i += 1


def _detect_partial_restarts(words, keep):
    """Strategy 2: adjacent segments split by 0.8 s gap — remove shorter prefix-match."""
    segments = []
    current = []
    for i, w in enumerate(words):
        if not keep[i]:
            continue
        if current and w["start"] - current[-1]["end"] > 0.8:
            segments.append(current)
            current = []
        current.append({**w, "idx": i})
    if current:
        segments.append(current)

    changed = True
    while changed:
        changed = False
        new_segs, skip = [], False
        for s in range(len(segments)):
            if skip:
                skip = False
                continue
            if s + 1 >= len(segments):
                new_segs.append(segments[s])
                continue
            a, b = segments[s], segments[s + 1]
            ta = "".join(w["text"] for w in a)
            tb = "".join(w["text"] for w in b)
            overlap = prefix_overlap(ta, tb)
            shorter = min(len(ta), len(tb))
            if shorter >= 2 and overlap / shorter > 0.5 and overlap >= 2:
                remove, kept = (a, b) if len(ta) <= len(tb) else (b, a)
                for w in remove:
                    keep[w["idx"]] = False
                new_segs.append(kept)
                skip = True
                changed = True
            else:
                new_segs.append(a)
        segments = new_segs


def _detect_continuous_restarts(words, keep):
    """Strategy 3: repeated 'takes' within continuous speech — keep longest."""
    n = len(words)
    kept_entries = [(i, words[i]) for i in range(n) if keep[i]]
    if len(kept_entries) < 5:
        return

    min_chars = 5
    texts = [w["text"] for _, w in kept_entries]

    groups = defaultdict(list)
    for ki in range(len(kept_entries)):
        forward = "".join(texts[ki:ki + 15])
        if len(forward) >= min_chars:
            groups[forward[:min_chars]].append(ki)

    take_starts = set()
    for positions in groups.values():
        if len(positions) >= 2:
            take_starts.update(positions)
    if not take_starts:
        return

    sorted_starts = sorted(take_starts)
    filtered = [sorted_starts[0]]
    last = sorted_starts[0]
    for s in sorted_starts[1:]:
        if s > last + 1:
            filtered.append(s)
        last = s

    takes = []
    for ti, start_ki in enumerate(filtered):
        end_ki = filtered[ti + 1] if ti + 1 < len(filtered) else len(kept_entries)
        tw = [{**kept_entries[ki][1], "idx": kept_entries[ki][0]}
              for ki in range(start_ki, end_ki)]
        takes.append({"words": tw, "text": "".join(w["text"] for w in tw)})

    changed = True
    while changed:
        changed = False
        new_takes, skip = [], False
        for ti in range(len(takes)):
            if skip:
                skip = False
                continue
            if ti + 1 >= len(takes):
                new_takes.append(takes[ti])
                continue
            a, b = takes[ti], takes[ti + 1]
            if prefix_overlap(a["text"], b["text"]) >= min_chars:
                remove, kept = (a, b) if len(a["text"]) <= len(b["text"]) else (b, a)
                for w in remove["words"]:
                    keep[w["idx"]] = False
                new_takes.append(kept)
                skip = True
                changed = True
            else:
                new_takes.append(a)
        takes = new_takes


def detect_stutters(words: list[dict]) -> tuple[list[dict], list[dict], list[bool]]:
    if not words:
        return [], [], []

    keep = [True] * len(words)
    _detect_exact_repeats(words, keep)
    _detect_partial_restarts(words, keep)
    _detect_continuous_restarts(words, keep)

    kept = [w for i, w in enumerate(words) if keep[i]]
    removed = [w for i, w in enumerate(words) if not keep[i]]
    if removed:
        print(f"[3/4] 找到 {len(removed)} 個重複/結巴的詞，將會移除：")
        for w in removed:
            print(f"   [{w['start']:.1f}s - {w['end']:.1f}s] \"{w['text']}\"")
    else:
        print("[3/4] 沒有偵測到結巴或重複的地方")
    return kept, words, keep


# ---------------------------------------------------------------------------
# Stutter detection — Gemini
# ---------------------------------------------------------------------------

GEMINI_PROMPT = """你是一位專業的影片剪輯師。以下是一段影片的逐字稿 JSON，每個詞都有時間戳。

請分析這份逐字稿，找出所有應該剪掉的部分：

1. 結巴與重複：同一句話說了多次 → 只保留最完整流暢的那一次
2. 說到一半重來：移除不完整的部分，保留完整的
3. 口頭禪贅字：「這個」「那個」當口頭禪、沒有指示意義時 → 移除
   例如「他的這個教學質量」→「這個」是贅字，移除；「這個問題很重要」→ 有指示意義，保留
4. 語氣填充：「就是說」「就是」「怎麼說呢」「嗯」「啊」「呃」「對」等不影響語意的 → 移除
5. 重複的連接詞或轉折詞 → 移除多餘的

判斷原則：移除後前後文依然通順就該移除。不要移除有實質語意、推進內容的詞。
{extra_rules}
請回傳一個 JSON 陣列，格式為：
[0, 3, 4, 5, 12, 13]

陣列中的數字是需要「移除」的詞的 index（i 欄位）。只回傳需要移除的 index，不需要其他文字說明。

逐字稿：
{transcript}"""


CHUNK_SIZE = 800
CHUNK_OVERLAP = 50


def _call_gemini(client, chunk: list[dict], extra_rules: str = "") -> set[int]:
    """Send one chunk to Gemini API, return set of word indices to remove."""
    transcript = json.dumps(chunk, ensure_ascii=False)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=GEMINI_PROMPT.format(transcript=transcript, extra_rules=extra_rules),
    )
    text = response.text.strip()
    if "```" in text:
        text = text[text.find("["):text.rfind("]") + 1]
    return set(json.loads(text))


def gemini_detect_stutters(words: list[dict], api_key: str,
                           remove_words: list[str] | None = None) -> tuple[list[dict], list[dict], list[bool]]:
    from google import genai

    client = genai.Client(api_key=api_key)

    extra_rules = ""
    if remove_words:
        joined = "、".join(f"「{w}」" for w in remove_words)
        extra_rules = f"\n特別注意：以下詞彙無論在什麼語境都必須移除：{joined}\n"

    entries = [
        {"i": i, "text": w["text"], "start": w["start"], "end": w["end"]}
        for i, w in enumerate(words)
    ]

    # Split into chunks with overlap to catch stutters at boundaries
    n = len(entries)
    if n <= CHUNK_SIZE:
        chunks = [entries]
    else:
        chunks = []
        start = 0
        while start < n:
            end = min(start + CHUNK_SIZE, n)
            chunks.append(entries[start:end])
            start = end - CHUNK_OVERLAP  # overlap with previous chunk
            if start + CHUNK_OVERLAP >= n:
                break

    total_chunks = len(chunks)
    if total_chunks == 1:
        print("[3/4] 請 Gemini AI 分析結巴、贅字、口頭禪...")
    else:
        print(f"[3/4] 逐字稿較長（{n} 個詞），分 {total_chunks} 批送 Gemini 分析...")

    remove_indices = set()
    for ci, chunk in enumerate(chunks):
        if total_chunks > 1:
            print(f"   分析第 {ci + 1}/{total_chunks} 批（詞 {chunk[0]['i']}～{chunk[-1]['i']}）...")
        result = _call_gemini(client, chunk, extra_rules)
        remove_indices.update(result)

    # Post-processing: force-remove words matching the list (Gemini safety net)
    # Supports multi-word concatenation: e.g. "民辦教師" matches "民"+"辦"+"教"+"師"
    if remove_words:
        for rw in remove_words:
            rw_len = len(rw)
            for i in range(n):
                concat = ""
                for j in range(i, n):
                    concat += words[j]["text"]
                    if len(concat) > rw_len:
                        break
                    if concat == rw:
                        for k in range(i, j + 1):
                            remove_indices.add(k)
                        break

    keep = [i not in remove_indices for i in range(n)]
    kept = [w for i, w in enumerate(words) if keep[i]]
    removed = [w for i, w in enumerate(words) if not keep[i]]
    if removed:
        print(f"   Gemini 標記了 {len(removed)} 個詞需要移除：")
        for w in removed:
            print(f"   [{w['start']:.1f}s - {w['end']:.1f}s] \"{w['text']}\"")
    else:
        print("   Gemini 沒有偵測到結巴或重複")
    return kept, words, keep


# ---------------------------------------------------------------------------
# Interval building
# ---------------------------------------------------------------------------

def build_keep_intervals(kept_words: list[dict], total_duration: float, padding: float = 0.05) -> list[tuple]:
    if not kept_words:
        return [(0, total_duration)]

    intervals = [
        (max(0, w["start"] - padding), min(total_duration, w["end"] + padding))
        for w in kept_words
    ]

    merged = [intervals[0]]
    for start, end in intervals[1:]:
        if start <= merged[-1][1] + 0.3:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    if 0 < merged[0][0] < 1.0:
        merged[0] = (0, merged[0][1])
    if 0 < total_duration - merged[-1][1] < 1.0:
        merged[-1] = (merged[-1][0], total_duration)

    return merged


# ---------------------------------------------------------------------------
# Video cutting with alternating zoom
# ---------------------------------------------------------------------------

def cut_video(video_path: str, intervals: list[tuple], output_path: str,
              zoom: float = 1.07, width: int = 1920, height: int = 1080):
    print("[4/4] 剪輯影片中...")
    if not intervals:
        print("   沒有需要剪輯的內容")
        return

    use_zoom = zoom > 1.0 and len(intervals) > 1

    with tempfile.TemporaryDirectory() as tmpdir:
        parts = []
        for i, (start, end) in enumerate(intervals):
            part_path = os.path.join(tmpdir, f"part_{i:04d}.ts")
            parts.append(part_path)

            cmd = [
                "ffmpeg", "-y", "-i", video_path,
                "-ss", str(start), "-t", str(end - start),
            ]
            if use_zoom and i % 2 == 1:
                cmd += ["-vf", f"scale={int(width * zoom)}:{int(height * zoom)},crop={width}:{height}"]
            cmd += [
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k",
                "-avoid_negative_ts", "make_zero",
                part_path,
            ]
            subprocess.run(cmd, capture_output=True)

        concat_file = os.path.join(tmpdir, "concat.txt")
        with open(concat_file, "w") as f:
            for part in parts:
                f.write(f"file '{part}'\n")

        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", concat_file, "-c", "copy", output_path],
            capture_output=True,
        )

    if use_zoom:
        zoomed = sum(1 for i in range(len(intervals)) if i % 2 == 1)
        print(f"   已套用 {int(zoom * 100)}% 縮放到 {zoomed} 個片段（模擬雙機位）")
    print(f"   完成！輸出檔案：{output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="自動剪掉影片中結巴、重複的片段")
    parser.add_argument("input", help="影片檔案路徑")
    parser.add_argument("-o", "--output", help="輸出檔案路徑（預設：原檔名_clean.mp4）")
    parser.add_argument("--model", default="medium",
                        help="語音辨識模型：tiny/base/small/medium/large-v3（預設：medium）")
    parser.add_argument("--transcript", action="store_true",
                        help="同時輸出逐字稿 JSON（可手動微調後重新剪輯）")
    parser.add_argument("--from-transcript", metavar="JSON",
                        help="從修改過的逐字稿 JSON 剪輯（跳過語音辨識）")
    args = parser.parse_args()
    config = load_config()

    input_path = args.input
    if not os.path.exists(input_path):
        print(f"\n   找不到影片檔案：{input_path}")
        print(f"   請確認檔案路徑是否正確，或把影片放到這個資料夾裡再試一次。\n")
        sys.exit(1)

    if args.output:
        output_path = args.output
    else:
        p = Path(input_path)
        output_path = str(p.parent / f"{p.stem}_clean{p.suffix}")

    # --- Detect stutters ---
    if args.from_transcript:
        json_path = args.from_transcript
        if not os.path.exists(json_path):
            print(f"\n   找不到逐字稿檔案：{json_path}")
            print(f"   請先用 --transcript 產出逐字稿，編輯後再用 --from-transcript 載入。\n")
            sys.exit(1)
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        all_words = [{"text": w["text"], "start": w["start"], "end": w["end"]} for w in data]
        keep_flags = [w["keep"] for w in data]
        kept_words = [w for w, k in zip(all_words, keep_flags) if k]
        removed = sum(1 for k in keep_flags if not k)
        print(f"[從逐字稿載入] 共 {len(all_words)} 個詞，其中 {removed} 個標記為移除")
    else:
        words = transcribe(input_path, args.model)
        api_key = config.get("gemini_api_key", "")
        remove_words = config.get("remove_words", [])
        if api_key:
            try:
                kept_words, all_words, keep_flags = gemini_detect_stutters(words, api_key, remove_words)
            except Exception as e:
                print(f"   Gemini 無法使用，改用本機分析（原因：{_friendly_error(e)}）")
                kept_words, all_words, keep_flags = detect_stutters(words)
        else:
            print("[3/4] 使用本機規則分析結巴（如需更精準，可在 config.json 設定 gemini_api_key）")
            kept_words, all_words, keep_flags = detect_stutters(words)

    # --- Build intervals & cut ---
    video_info = get_video_info(input_path)
    duration = video_info["duration"]
    intervals = build_keep_intervals(kept_words, duration)

    kept_duration = sum(e - s for s, e in intervals)
    saved = duration - kept_duration
    print(f"\n   原始長度：{duration:.1f} 秒 → 剪後長度：{kept_duration:.1f} 秒（省了 {saved:.1f} 秒）")

    zoom = config.get("zoom", 1.07)
    cut_video(input_path, intervals, output_path,
              zoom=zoom, width=video_info["width"], height=video_info["height"])

    # --- Optional transcript output ---
    if args.transcript:
        transcript_path = str(Path(output_path).with_suffix(".json"))
        out = [{**w, "keep": k} for w, k in zip(all_words, keep_flags)]
        with open(transcript_path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"   逐字稿已輸出：{transcript_path}")


def _friendly_error(e: Exception) -> str:
    """Turn API exceptions into short, user-friendly messages."""
    msg = str(e)
    if "API_KEY_INVALID" in msg or "API key not valid" in msg:
        return "API 金鑰無效，請檢查 config.json 裡的 gemini_api_key 是否正確"
    if "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower():
        return "Gemini 免費額度已用完，請稍後再試或改用付費方案"
    if "PERMISSION_DENIED" in msg:
        return "沒有權限使用 Gemini API，請確認 API 金鑰的權限設定"
    if "connect" in msg.lower() or "timeout" in msg.lower() or "network" in msg.lower():
        return "網路連線失敗，請檢查網路後再試"
    return f"發生錯誤 — {msg[:100]}"


if __name__ == "__main__":
    main()
