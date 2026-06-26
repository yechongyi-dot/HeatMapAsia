# HeatMap-Asia — 日本・韓国・シンガポール投資動画ランキング

YouTube・ニコニコ動画の投資動画をスクレイピングし、熱度スコアでランキングするデスクトップアプリ。
**日本 🇯🇵 / 韓国 🇰🇷 / シンガポール 🇸🇬** の3市場を、画面上部の地域スイッチャーで切り替えられます。

> 元の単一市場版「HeatMap」とは完全に独立しています（別フォルダ・別データベース）。両方を同時にインストール・実行できます。

---

## 対応市場とデータソース

| 地域 | キーワード言語 | データソース |
|------|----------------|--------------|
| 🇯🇵 日本 | 日本語 | YouTube・ニコニコ動画・公式チャンネル（日銀/財務省/JPX/日経CNBC ほか） |
| 🇰🇷 韓国 | 한국어 | YouTube・公式チャンネル（한국은행/KRX/기획재정부/한국경제TV ほか） |
| 🇸🇬 シンガポール | English | YouTube・公式チャンネル（MAS/SGX/The Business Times/CNA） |

ニコニコは日本専用です。地域ごとに検索キーワード・タイトル判定・公式チャンネル・言語ボーナスを切り替えます（`scraper/regions.py`）。

---

## 必要環境

| 項目 | 要件 |
|------|------|
| OS | Windows 10 / 11（64ビット） |
| Python | **3.10 以上**（3.10未満では起動しない） |
| ffmpeg | PATH に通っていること（下記参照） |

### ffmpeg のインストール

```bat
winget install ffmpeg
```

またはバイナリを直接 [ffmpeg.org](https://ffmpeg.org/download.html) からダウンロードして PATH に追加。

> **なぜ必要？**  
> - `bestvideo+bestaudio` 形式のダウンロードで映像・音声を結合するため  
> - 素材ライブラリのサムネイル生成（フレーム抽出）のため

---

## インストール

```bat
pip install -r requirements.txt
```

---

## 起動方法

**ダブルクリック:**
```
launch.bat
```

**コマンドライン:**
```bat
python main.py
```

---

## 毎日自動スクレイピング（Windows タスクスケジューラ）

| 設定項目 | 値 |
|----------|----|
| プログラム | `python` |
| 引数 | `scheduler\daily_job.py` |
| **起始目录（重要）** | `C:\path\to\hm`（プロジェクトのルートフォルダ） |

---

## データ保存場所

```
%LOCALAPPDATA%\HeatMapAsia\
├── data\videos_v2.db    # SQLite データベース（地域は region 列で区別）
├── downloads\           # ダウンロード動画（変更可）
├── thumbnails\          # サムネイル
└── cookies.txt          # ニコニコ用 Cookie（任意）
```

`HEATMAPASIA_DATA_DIR` 環境変数で変更可能。元の HeatMap (`%LOCALAPPDATA%\HeatMap\`) とは別ディレクトリなので干渉しません。

---

## ニコニコ動画のログイン（任意）

会員限定動画をダウンロードしたい場合、ブラウザ拡張 [Get cookies.txt](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) でエクスポートした `cookies.txt` を以下に配置：

```
%LOCALAPPDATA%\HeatMapAsia\cookies.txt
```

---

## 在线更新 (Online update)

パッケージ版（`HeatMapAsia.exe`）は GitHub Releases (`yechongyi-dot/HeatMapAsia`) を見て自動更新します。再インストール不要。

- **起動時**：新しいバージョンがあれば確認ダイアログを表示 → 「立即更新」で自動ダウンロード＆再起動。
- **手動**：右上のバージョンチップ（`v0.1.0`）をクリックして更新チェック。

仕組み：実行中の `.exe` は自身を上書きできないため、新ビルドを一時フォルダへ展開し、アプリ終了後にバッチスクリプトがファイルを差し替えて再起動します（ユーザーデータは `%LOCALAPPDATA%\HeatMapAsia\` にあるため影響なし）。

> リリース用の GitHub リポジトリ `yechongyi-dot/HeatMapAsia` は初回配信前に作成してください（未作成の間は更新チェックが静かに失敗するだけです）。

> 開発モード（`python main.py`）では在線更新は無効です（`git pull` を使用）。

---

## ビルドとリリース（メンテナ向け）

```bat
pip install pyinstaller
```

`vendor_ffmpeg/` は容量の都合で Git 管理対象外です。ビルド前に以下のファイルを `vendor_ffmpeg/` に配置してください（リポジトリには含まれません）：

```
vendor_ffmpeg\ffmpeg.exe  ffprobe.exe  avcodec-*.dll  avformat-*.dll  avutil-*.dll
              avfilter-*.dll  avdevice-*.dll  swresample-*.dll  swscale-*.dll
```

新バージョンを配信する手順：

1. `version.py` の `__version__` を上げる（例: `0.1.0` → `0.2.0`）
2. リリーススクリプトを実行（PyInstaller ビルド → zip → `gh release create`）：

```bat
python scripts\release.py
```

これで既存のクライアントは次回起動時に更新を検知します。`gh` の認証が必要です（`gh auth login`）。
