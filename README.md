# Tech News Daily Bot

IT・テック関連ニュースを毎朝自動収集し、メールとWebサイトで配信する仕組み。

## 構成概要

```
RSSフィード（20+ソース）
    ↓ feedparser で取得
Pythonスクリプト（過去24時間・カテゴリごとに厳選）
    ↓ Claude API で日本語要約（任意）
HTML生成
    ├── Gmail SMTP でメール送信
    └── GitHub Pages で公開（アーカイブ閲覧用）
```

## カテゴリとソース

| カテゴリ | 主なソース |
|---|---|
| AI・機械学習 | Anthropic, OpenAI, Google AI, MIT Tech Review, HN |
| Web開発 | Smashing Magazine, CSS-Tricks, Zenn, Qiita |
| .NET・C# | .NET Blog, ASP.NET Blog, Visual Studio Blog, Zenn |
| セキュリティ | The Hacker News, Krebs, JPCERT, IPA |
| ガジェット・テック | The Verge, TechCrunch, ITmedia, Engadget |

ソースは `config/feeds.yml` で自由に追加・削除できる。

## セットアップ手順

### 1. リポジトリ作成

このディレクトリごとGitHubにpushする。リポジトリはprivateでもOK。

```bash
cd tech-news-bot
git init
git add .
git commit -m "initial commit"
git branch -M main
git remote add origin https://github.com/<あなたのユーザー名>/tech-news-bot.git
git push -u origin main
```

### 2. GitHub Pages を有効化

1. リポジトリの Settings → Pages を開く
2. Source を「GitHub Actions」に設定
3. 初回実行後、`https://<ユーザー名>.github.io/tech-news-bot/` で閲覧可能

### 3. Secrets を登録（Settings → Secrets and variables → Actions）

| キー | 用途 | 必須 |
|---|---|---|
| `ANTHROPIC_API_KEY` | AI要約用APIキー | 任意（未設定ならRSS要約のみ） |
| `EMAIL_FROM` | 送信元Gmailアドレス | メール送信する場合 |
| `EMAIL_TO` | 受信先メールアドレス | メール送信する場合 |
| `EMAIL_APP_PASSWORD` | Gmailのアプリパスワード | メール送信する場合 |

#### Gmailアプリパスワードの取得方法

1. Googleアカウントで2段階認証を有効化
2. https://myaccount.google.com/apppasswords にアクセス
3. アプリ名を「Tech News Bot」などで作成
4. 表示された16桁の文字列を `EMAIL_APP_PASSWORD` に登録

#### Anthropic APIキーの取得方法

1. https://console.anthropic.com/ にサインアップ
2. API Keys から発行
3. 要約に使うのは Claude Haiku 4.5 で、1日40記事の要約でも月数十円程度

### 4. 動作確認

GitHub Actions の画面から「Daily Tech News」ワークフローを手動実行（Run workflow）して確認する。

## ローカル実行

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-xxx  # 任意
python src/main.py
# → docs/index.html が生成される
open docs/index.html
```

## スケジュール変更

`.github/workflows/daily-news.yml` の cron を編集する。UTC基準なので注意。

```yaml
# 毎日 朝7時(JST) = 22時UTC
- cron: '0 22 * * *'

# 平日のみ 朝8時(JST) = 23時UTC
- cron: '0 23 * * 1-5'
```

## 運用コスト

| 項目 | 費用 |
|---|---|
| GitHub Actions | **無料**（public: 無制限 / private: 月2,000分無料枠で十分） |
| GitHub Pages | **無料** |
| Gmail SMTP | **無料** |
| Claude API (Haiku) | 月100円程度（40記事/日の要約） |

## 拡張アイディア

- Slack Webhook でチーム配信（`src/send_slack.py` を追加するだけ）
- 記事の重複検知（Zenn/Qiita/HNで同じ記事が複数ヒットする場合に名寄せ）
- キーワードフィルタ（`config/feeds.yml` に `exclude_keywords` を追加）
- 既読管理（Pagesにチェックボックス機能を追加し、`localStorage`で保持）
