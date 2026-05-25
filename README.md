# Lyria Realtime BGM System

自然文入力からBGMを自動設定し、再生中にリアルタイム調整できるローカル実行システムです。  
フロントエンドは `figma/`（React + Vite）、バックエンドは `local_control_server.py`（FastAPI）です。

## 実行環境（本制作）

- OS: macOS 15.6.1 (Build 24G90)
- Python: 3.12.10
- Node.js: v22.17.0
- npm: 11.4.2
- fastapi: 0.136.1
- uvicorn: 0.47.0
- google-genai: 2.4.0
- sounddevice: 0.5.5
- numpy: 2.0.2

確認:

```bash
python3 --version
node --version
npm --version
```

## セットアップ

リポジトリをクローンして、ルートディレクトリに移動:

```bash
git clone <YOUR_REPOSITORY_URL>
cd <YOUR_REPOSITORY_DIR>
```

### 1) Python依存のインストール

```bash
python3 -m pip install "fastapi==0.136.1" "uvicorn==0.47.0" "google-genai==2.4.0" "sounddevice==0.5.5" "numpy==2.0.2"
```

### 2) フロント依存のインストール

```bash
cd figma
npm ci
cd ..
```

## 環境変数

必須:

```bash
export GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
```

任意:

```bash
# Planner model
export GEMINI_PLANNER_MODEL="gemini-3.1-flash-lite"

# 出力デバイスID（例: 5 = 複数出力装置）
export LYRIA_OUTPUT_DEVICE_ID="5"
```

## 実行手順

### ターミナルA（バックエンド）

```bash
uvicorn local_control_server:app --host 127.0.0.1 --port 8001
```

### ターミナルB（フロントエンド）

```bash
cd figma
npm run dev
```

ブラウザで開く:

- `http://127.0.0.1:5173`

## 使い方

1. `Auto Setup Request` に自然文を入力（例: `勉強用のBGMをかけて`）
2. `Auto Setup` を押す
3. `Generate & Play` で再生開始
4. 再生中に `Tempo / Brightness / Density / Key` を調整

## 動作確認API

```bash
curl http://127.0.0.1:8001/api/status
curl http://127.0.0.1:8001/api/planner-log
```

## よくあるエラー

### `GEMINI_API_KEY is not set`

```bash
export GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
```

### 音が出ない

出力デバイスIDを確認:

```bash
python3 - <<'PY'
import sounddevice as sd
for i, d in enumerate(sd.query_devices()):
    if d["max_output_channels"] > 0:
        print(i, d["name"])
PY
```

表示されたIDを `LYRIA_OUTPUT_DEVICE_ID` に設定してサーバーを再起動してください。
