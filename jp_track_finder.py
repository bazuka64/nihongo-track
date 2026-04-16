"""
JP Audio Track Finder
指定チャンネルの動画を全スキャンして、日本語音声トラックがある動画だけ表示する。
yt-dlp が必要: pip install yt-dlp

検出方法:
  YouTube の自動吹き替え音声トラック (isAutoDubbed) は yt-dlp の formats に
  出てこないため、動画ページの HTML から audioTrack JSON を直接スクレイピングして
  "id":"ja." エントリの有無で判定する。

タイトル翻訳:
  Google Translate 非公式エンドポイントを urllib で叩く（API キー不要）。
"""

import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import json
import re
import threading
import webbrowser
import urllib.request
import urllib.parse

CHANNEL_URL = "https://www.youtube.com/@bigboxSWE/videos"


class JpTrackFinder:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("JP Audio Track Finder")
        self.root.geometry("1000x640")
        self.root.minsize(750, 460)

        self.found: list[tuple[str, str, str]] = []  # (ja_title, en_title, url)
        self._stop_flag = threading.Event()
        self._scan_thread: threading.Thread | None = None

        self._build_ui()

    # ------------------------------------------------------------------ UI --
    def _build_ui(self):
        # ---- channel URL bar ----
        url_bar = tk.Frame(self.root, pady=4)
        url_bar.pack(fill=tk.X, padx=10)

        tk.Label(url_bar, text="チャンネルURL:").pack(side=tk.LEFT)
        self.entry_url = tk.Entry(url_bar, font=("", 10))
        self.entry_url.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        # ---- top bar ----
        top = tk.Frame(self.root, pady=4)
        top.pack(fill=tk.X, padx=10)

        self.btn_scan = tk.Button(top, text="スキャン開始", width=14,
                                  command=self._start_scan)
        self.btn_scan.pack(side=tk.LEFT)

        self.btn_stop = tk.Button(top, text="停止", width=8,
                                  command=self._stop_scan, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=4)

        self.btn_save = tk.Button(top, text="URLを保存", width=10,
                                  command=self._save_urls, state=tk.DISABLED)
        self.btn_save.pack(side=tk.LEFT, padx=4)

        self.lbl_status = tk.Label(top, text="準備完了", anchor=tk.W,
                                   fg="#555555")
        self.lbl_status.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

        self.lbl_count = tk.Label(top, text="JP音声: 0件", fg="#006600",
                                  font=("", 10, "bold"))
        self.lbl_count.pack(side=tk.RIGHT)

        # ---- progress bar ----
        self.pb = ttk.Progressbar(self.root, mode="indeterminate")
        self.pb.pack(fill=tk.X, padx=10, pady=(0, 4))

        # ---- treeview ----
        tree_frame = tk.Frame(self.root)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10)

        cols = ("ja_title", "en_title", "url")
        self.tree = ttk.Treeview(tree_frame, columns=cols,
                                 show="headings", selectmode="browse")
        self.tree.heading("ja_title", text="タイトル（日本語）")
        self.tree.heading("en_title", text="原題（英語）")
        self.tree.heading("url",      text="URL")
        self.tree.column("ja_title", width=340, stretch=True)
        self.tree.column("en_title", width=300, stretch=True)
        self.tree.column("url",      width=200, stretch=False)

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL,
                             command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<Double-Button-1>", self._open_browser)
        self.tree.bind("<Return>",          self._open_browser)

        # ---- bottom bar ----
        bot = tk.Frame(self.root, pady=5)
        bot.pack(fill=tk.X, padx=10)

        tk.Button(bot, text="ブラウザで開く (ダブルクリックでも可)",
                  command=self._open_browser).pack(side=tk.LEFT)

        tk.Button(bot, text="URLをクリップボードにコピー",
                  command=self._copy_url).pack(side=tk.LEFT, padx=6)

        # ---- log ----
        log_frame = tk.LabelFrame(self.root, text="ログ", padx=4, pady=2)
        log_frame.pack(fill=tk.X, padx=10, pady=(2, 6))

        self.log_box = tk.Text(log_frame, height=5, state=tk.DISABLED,
                               font=("Consolas", 9), wrap=tk.WORD,
                               bg="#f5f5f5")
        self.log_box.pack(fill=tk.X)

    # ---------------------------------------------------------------- scan --
    def _start_scan(self):
        channel_url = self.entry_url.get().strip()
        if not channel_url:
            messagebox.showwarning("入力エラー", "チャンネルURLを入力してください。")
            return
        # /featured や末尾スラッシュを /videos に正規化
        channel_url = re.sub(r"/(featured|about|community|shorts)$", "", channel_url.rstrip("/"))
        if not channel_url.endswith("/videos"):
            channel_url = channel_url.rstrip("/") + "/videos"
        self._channel_url = channel_url

        self._stop_flag.clear()
        self.found.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.lbl_count.config(text="JP音声: 0件")
        self.btn_scan.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.btn_save.config(state=tk.DISABLED)
        self.pb.start(10)
        self._log("=== スキャン開始 ===")

        self._scan_thread = threading.Thread(target=self._scan_worker,
                                             daemon=True)
        self._scan_thread.start()

    def _stop_scan(self):
        self._stop_flag.set()

    def _finish_scan(self, aborted: bool = False):
        self.pb.stop()
        self.btn_scan.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        if self.found:
            self.btn_save.config(state=tk.NORMAL)
        msg = "中断しました" if aborted else "スキャン完了"
        self._set_status(msg)
        self._log(f"=== {msg} / JP音声あり: {len(self.found)}件 ===")

    def _scan_worker(self):
        # 1. チャンネルの動画リストを取得
        channel_url = self._channel_url
        self._set_status("動画リストを取得中...")
        self._log(f"対象: {channel_url}")

        try:
            proc = subprocess.run(
                ["yt-dlp", "--flat-playlist", "-J", "--no-warnings",
                 channel_url],
                capture_output=True, text=True, timeout=120
            )
        except subprocess.TimeoutExpired:
            self._log("[エラー] タイムアウト: チャンネル取得")
            self.root.after(0, self._finish_scan, True)
            return
        except FileNotFoundError:
            self._log("[エラー] yt-dlp が見つかりません。pip install yt-dlp")
            self.root.after(0, self._finish_scan, True)
            return

        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            self._log("[エラー] JSONパース失敗。yt-dlp の出力を確認してください。")
            self.root.after(0, self._finish_scan, True)
            return

        entries = data.get("entries") or []
        # flat-playlist がネストされているケースを flatten
        flat: list[dict] = []
        for e in entries:
            if e and e.get("_type") == "playlist":
                flat.extend(e.get("entries") or [])
            elif e:
                flat.append(e)

        total = len(flat)
        self._log(f"動画数: {total}件  — 1本ずつ確認します")

        # 2. 各動画を確認
        for i, entry in enumerate(flat):
            if self._stop_flag.is_set():
                break

            vid_id = entry.get("id") or entry.get("url", "").split("=")[-1]
            en_title = entry.get("title", "(タイトル不明)")
            url      = (entry.get("url") or f"https://www.youtube.com/watch?v={vid_id}")
            if not url.startswith("http"):
                url = f"https://www.youtube.com/watch?v={url}"

            short = en_title[:40] + ("..." if len(en_title) > 40 else "")
            self._set_status(f"[{i+1}/{total}] {short}")

            if self._has_japanese_audio(url):
                ja_title = self._translate(en_title)
                self.root.after(0, self._add_row, ja_title, en_title, url)
                self._log(f"JP [{i+1}/{total}] {ja_title}")

        aborted = self._stop_flag.is_set()
        self.root.after(0, self._finish_scan, aborted)

    # -------------------------------------------------- detection & translate
    _YT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en;q=0.9",
    }
    # "id":"ja.10" や "id":"ja-JP.10" にマッチ
    _JA_AUDIO_RE = re.compile(r'"id"\s*:\s*"ja[\.\-]')

    def _has_japanese_audio(self, url: str) -> bool:
        """YouTube ページ HTML をスクレイピングして日本語 audioTrack を検出する。
        yt-dlp の formats には自動吹き替えトラックが出ないため HTML から直接確認する。"""
        try:
            req = urllib.request.Request(url, headers=self._YT_HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            return bool(self._JA_AUDIO_RE.search(html))
        except Exception:
            return False

    def _translate(self, text: str) -> str:
        """Google Translate 非公式エンドポイントで英語→日本語翻訳。失敗時は原文を返す。"""
        try:
            q   = urllib.parse.quote(text)
            url = (
                f"https://translate.googleapis.com/translate_a/single"
                f"?client=gtx&sl=en&tl=ja&dt=t&q={q}"
            )
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            # result[0] は [[翻訳文, 原文, ...], ...] のリスト
            return "".join(seg[0] for seg in result[0] if seg[0])
        except Exception:
            return text  # 翻訳失敗時は原文をそのまま返す

    # ---------------------------------------------------------- UI helpers --
    def _add_row(self, ja_title: str, en_title: str, url: str):
        self.found.append((ja_title, en_title, url))
        self.tree.insert("", tk.END, values=(ja_title, en_title, url))
        self.lbl_count.config(text=f"JP音声: {len(self.found)}件")

    def _set_status(self, msg: str):
        self.root.after(0, lambda: self.lbl_status.config(text=msg))

    def _log(self, msg: str):
        def _do():
            self.log_box.config(state=tk.NORMAL)
            self.log_box.insert(tk.END, msg + "\n")
            self.log_box.see(tk.END)
            self.log_box.config(state=tk.DISABLED)
        self.root.after(0, _do)

    def _selected_url(self) -> str | None:
        sel = self.tree.selection()
        if not sel:
            return None
        return self.tree.item(sel[0])["values"][2]

    def _open_browser(self, _event=None):
        url = self._selected_url()
        if url:
            webbrowser.open(url)
        else:
            messagebox.showinfo("ヒント", "動画を選択してからダブルクリックしてください。")

    def _copy_url(self):
        url = self._selected_url()
        if url:
            self.root.clipboard_clear()
            self.root.clipboard_append(url)
            self._log(f"コピー: {url}")
        else:
            messagebox.showinfo("ヒント", "動画を選択してください。")

    def _save_urls(self):
        if not self.found:
            return
        out_path = "jp_audio_videos.txt"
        with open(out_path, "w", encoding="utf-8") as f:
            for ja_title, en_title, url in self.found:
                f.write(f"{ja_title}\n{en_title}\n{url}\n\n")
        self._log(f"保存しました -> {out_path}")
        messagebox.showinfo("保存完了", f"{out_path} に保存しました。")


# -------------------------------------------------------------------- main --
if __name__ == "__main__":
    root = tk.Tk()
    app = JpTrackFinder(root)
    root.mainloop()
