# GitHub Actions セットアップガイド

## 概要
このスクリプトは毎日朝7:30（日本時間）にGitHub Actions上で自動実行されます。

---

## セットアップ手順

### ステップ1：GitHub Secretsに認証情報を登録

1. GitHub リポジトリを開く：
   ```
   https://github.com/susuheihei-lgtm/-
   ```

2. **Settings** → **Secrets and variables** → **Actions** をクリック

3. **New repository secret** をクリック

4. 以下の内容を登録：
   - **Name:** `GMAIL_CREDENTIALS`
   - **Secret:** `credentials.json` の内容をコピー&ペースト

   `credentials.json` の内容確認：
   ```bash
   cat credentials.json
   ```

5. **Add secret** をクリック

---

## 動作確認

### 手動実行テスト

1. GitHubで「Actions」タブをクリック
2. 左から「Auto Send Todo List」を選択
3. **Run workflow** ボタンをクリック
4. メールが届いたか確認

### 自動実行確認

- 毎日朝7:30 JST に自動実行されます
- **Actions** タブで実行ログを確認可能

---

## トラブルシューティング

### メールが送信されない場合

1. **Actions** タブで最新の実行をクリック
2. ログを確認（エラーメッセージを確認）
3. よくあるエラー：
   - `GMAIL_CREDENTIALS not found` → Secretsを確認
   - `Authentication failed` → `credentials.json` が正しいか確認

### 実行時刻を変更したい場合

`.github/workflows/auto-send-todo.yml` の以下の行を編集：

```yaml
- cron: '30 22 * * *'  # 現在：朝7:30 JST
```

**時刻変換表（UTC時刻）：**
- 朝8:00 JST → `0 23 * * *`
- 朝9:00 JST → `0 0 * * *`
- 朝6:00 JST → `0 21 * * *`

編集後、`git push` で自動反映

---

## セキュリティに関する注意

✅ `credentials.json` は GitHub Secrets で安全に暗号化されています
⚠️ リポジトリを公開にしないでください（パブリック設定の場合）

---

準備完了！毎日朝7:30に自動送信が開始されます。
