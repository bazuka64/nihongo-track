# nihongo-track

YouTubeチャンネルの動画を全スキャンして、**日本語音声トラック（自動吹き替え）がある動画だけ**を一覧表示するツール。

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)

## 概要

YouTubeには一部の動画に自動吹き替え機能（`isAutoDubbed`）があり、日本語を含む複数言語の音声トラックが用意されている。  
このツールはチャンネルURLを入力するだけで対象動画を自動的に絞り込み、日本語タイトル訳とともに一覧表示する。

## 機能

- チャンネルURLを入力して全動画をスキャン
- 日本語音声トラックがある動画のみ表示
- タイトルを日本語に自動翻訳（Google Translate 利用、APIキー不要）
- ダブルクリックでブラウザ再生
- 結果をテキストファイルに保存

## 動作要件

- Python 3.10+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)

```bash
pip install yt-dlp
```

## 使い方

```bash
python jp_track_finder.py
```

1. チャンネルURLを入力（例: `https://www.youtube.com/@bigboxSWE`）
2. 「スキャン開始」をクリック
3. 日本語音声つきの動画が見つかり次第リストに追加される
4. ダブルクリックでブラウザ再生

## 技術メモ

YouTube の自動吹き替え音声トラックは `yt-dlp` のフォーマット一覧には出てこない。  
動画ページの HTML に埋め込まれた `audioTrack` JSON を直接スクレイピングし、`"id":"ja."` の有無で判定している。
