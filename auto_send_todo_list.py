#!/usr/bin/env python3
"""
日本マスタートラスト信託銀行関連の自動ToDoリスト送信スクリプト
Gmailからメールを検索し、ToDoリストを作成して自動送信
"""

import os
import pickle
import re
import json
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import base64
from email.mime.text import MIMEText
import html

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.send']

# 設定ファイルを読み込む
with open('config.json', 'r', encoding='utf-8') as f:
    CONFIG = json.load(f)

def authenticate():
    """OAuth 2.0 認証"""
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return creds

def get_email_content(service, message_id):
    """メール内容を取得"""
    try:
        msg = service.users().messages().get(userId='me', id=message_id, format='full').execute()
        headers = msg['payload']['headers']
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
        sender = next((h['value'] for h in headers if h['name'] == 'From'), '')
        date_str = next((h['value'] for h in headers if h['name'] == 'Date'), '')

        # 受信日をパース
        try:
            received_date = parsedate_to_datetime(date_str)
        except:
            received_date = datetime.now()

        # メール本文を取得
        body = ''
        if 'parts' in msg['payload']:
            for part in msg['payload']['parts']:
                if part['mimeType'] == 'text/plain':
                    if 'data' in part['body']:
                        body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                    break
        else:
            if 'body' in msg['payload'] and 'data' in msg['payload']['body']:
                body = base64.urlsafe_b64decode(msg['payload']['body']['data']).decode('utf-8')

        return {
            'subject': subject,
            'sender': sender,
            'received_date': received_date,
            'body': body,
            'id': message_id
        }
    except:
        return None

def search_emails(service, query, max_results=50):
    """メールを検索"""
    try:
        results = service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
        return results.get('messages', [])
    except Exception as e:
        print(f"検索エラー: {e}")
        return []

def has_deadline_text(text):
    """テキストに「締切」の文言があるかチェック"""
    return '締切' in text

def extract_deadline_date(text, received_date):
    """テキストから締切日付を抽出（受信日の年を基準に）"""
    date_pattern = r'(\d{4}[/-]\d{1,2}[/-]\d{1,2}|\d{1,2}[/-]\d{1,2})'
    dates = re.findall(date_pattern, text)

    if not dates:
        return None

    try:
        date_str = dates[0]
        if '/' in date_str:
            date_str = date_str.replace('/', '-')

        if len(date_str.split('-')[0]) == 4:
            # YYYY-MM-DD形式（既に年が指定されている）
            return datetime.strptime(date_str, '%Y-%m-%d')
        else:
            # MM-DD形式（年が指定されていない）
            # メール受信日の年を使用
            due_date = datetime.strptime(date_str, '%m-%d')
            received_year = received_date.year if hasattr(received_date, 'year') else datetime.now().year
            return due_date.replace(year=received_year)
    except:
        return None

def extract_tasks_from_emails(emails):
    """メールからタスクを抽出（受信日が6ヶ月以内のみ）"""
    tasks = []
    six_months_ago = datetime.now() - timedelta(days=180)

    for email in emails:
        # 受信日が6ヶ月以内かチェック（タイムゾーン情報を削除）
        received_date = email['received_date'].replace(tzinfo=None) if hasattr(email['received_date'], 'tzinfo') else email['received_date']
        if received_date < six_months_ago:
            continue

        subject = email['subject']
        body = email['body']
        full_text = subject + '\n' + body

        # 「締切」の有無を判定
        has_deadline = has_deadline_text(full_text)

        # 締切日付を抽出（受信日の年を基準に）
        due_date = extract_deadline_date(full_text, received_date)

        # タスク情報を作成
        task_text = subject if subject.strip() else body[:100]

        tasks.append({
            'text': task_text,
            'subject': subject,
            'sender': email['sender'],
            'received_date': email['received_date'],
            'has_deadline': has_deadline,
            'due_date': due_date,
            'body': body
        })

    return tasks

def categorize_tasks(tasks):
    """タスクを「要確認」（締切あり）と「リマインド」（締切なし）に分類"""
    confirm = []   # 締切あり
    remind = []    # 締切なし

    for task in tasks:
        if task['has_deadline']:
            confirm.append(task)
        else:
            remind.append(task)

    # 要確認：締切が近いものから上に（降順 - 新しい日付から）
    confirm.sort(key=lambda x: x['due_date'] if x['due_date'] else datetime.min, reverse=True)

    # リマインド：受信日が新しいものから（降順）
    remind.sort(key=lambda x: x['received_date'], reverse=True)

    return confirm, remind

def create_todo_html(confirm_tasks, remind_tasks):
    """HTMLフォーマットのToDoリストを作成"""
    html_content = """
    <html>
      <head>
        <meta charset="utf-8">
        <style>
          body { font-family: 'Segoe UI', 'Arial', sans-serif; line-height: 1.6; }
          h2 { color: #fff; padding: 10px; margin: 15px 0 10px 0; border-radius: 5px; }
          .confirm-header { background-color: #ff6b6b; }
          .remind-header { background-color: #4a90e2; }
          .confirm-item { background-color: #ffe0e0; padding: 12px; margin: 8px 0; border-left: 4px solid #ff0000; border-radius: 3px; }
          .remind-item { background-color: #e8f0ff; padding: 12px; margin: 8px 0; border-left: 4px solid #4a90e2; border-radius: 3px; }
          .task-title { font-weight: bold; color: #333; font-size: 14px; margin-bottom: 5px; }
          .task-date { color: #666; font-size: 12px; }
          .task-sender { color: #999; font-size: 11px; margin-top: 3px; }
        </style>
      </head>
      <body>
        <p>お疲れ様です。</p>
        <p>日本マスタートラスト信託銀行からのメール対応事項をまとめました。</p>
    """

    # 要確認タスク（締切あり）
    if confirm_tasks:
        html_content += '<h2 class="confirm-header">⚠️ 【要確認】締切がある案件</h2>'
        for task in confirm_tasks:
            due_str = task['due_date'].strftime('%Y年%m月%d日') if task['due_date'] else '日付未記載'
            # メール本文プレビュー（最初の200文字）
            body_preview = task['body'].replace('\n', ' ').replace('\r', '')[:200].strip()
            if not body_preview:
                body_preview = '（本文なし）'

            html_content += f"""
            <div class="confirm-item">
              <div class="task-title">{html.escape(task['text'][:100])}</div>
              <div class="task-date">📅 締切: {due_str}</div>
              <div style="color: #555; font-size: 13px; margin: 8px 0; padding: 8px; background-color: #fff5e6; border-radius: 3px;">
                📝 {html.escape(body_preview)}
              </div>
              <div class="task-sender">From: {html.escape(task['sender'][:60])}</div>
            </div>
            """

    # リマインドタスク（締切なし）
    if remind_tasks:
        html_content += '<h2 class="remind-header">📌 【リマインド】その他のお知らせ</h2>'
        for task in remind_tasks:
            received_str = task['received_date'].strftime('%Y年%m月%d日')
            # メール本文プレビュー（最初の200文字）
            body_preview = task['body'].replace('\n', ' ').replace('\r', '')[:200].strip()
            if not body_preview:
                body_preview = '（本文なし）'

            html_content += f"""
            <div class="remind-item">
              <div class="task-title">{html.escape(task['text'][:100])}</div>
              <div class="task-date">📧 受信日: {received_str}</div>
              <div style="color: #555; font-size: 13px; margin: 8px 0; padding: 8px; background-color: #f0f8ff; border-radius: 3px;">
                📝 {html.escape(body_preview)}
              </div>
              <div class="task-sender">From: {html.escape(task['sender'][:60])}</div>
            </div>
            """

    html_content += """
        <br>
        <p style="color: #999; font-size: 12px;">このメールは自動生成されています。</p>
      </body>
    </html>
    """

    return html_content

def send_email(to_address, subject, body_html):
    """メールを送信"""
    creds = authenticate()
    service = build('gmail', 'v1', credentials=creds)

    message = MIMEText(body_html, 'html')
    message['to'] = to_address
    message['subject'] = subject

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

    try:
        send_message = service.users().messages().send(
            userId='me',
            body={'raw': raw_message}
        ).execute()

        print(f"✅ ToDoリストメール送信成功！")
        print(f"   宛先: {to_address}")
        print(f"   件名: {subject}")
        return True
    except Exception as e:
        print(f"❌ エラー: {e}")
        return False

if __name__ == '__main__':
    creds = authenticate()
    service = build('gmail', 'v1', credentials=creds)

    # 設定ファイルから読み込む
    company_name = CONFIG['company_name']
    search_email = CONFIG['search']['email']
    exclude_emails = CONFIG['search']['exclude_emails']
    max_results = CONFIG['search']['max_results']
    recipients = CONFIG['email']['recipients']

    # 検索クエリを生成
    exclude_query = ' '.join([f'-from:{e}' for e in exclude_emails])
    query = f'{search_email} {exclude_query}'

    emails_data = search_emails(service, query, max_results=max_results)

    if not emails_data:
        print("関連メールが見つかりません")
        exit(1)

    # メール内容を取得
    emails = []
    for email_data in emails_data:
        email_content = get_email_content(service, email_data['id'])
        if email_content:
            emails.append(email_content)

    # タスクを抽出
    tasks = extract_tasks_from_emails(emails)

    if not tasks:
        print("タスクが見つかりません")
        exit(1)

    # タスクを分類
    confirm_tasks, remind_tasks = categorize_tasks(tasks)

    # HTMLリストを作成
    todo_html = create_todo_html(confirm_tasks, remind_tasks)

    # メール送信
    today = datetime.now().strftime('%Y/%m/%d')
    subject = CONFIG['email']['subject_template'].format(
        company_name=company_name,
        date=today
    )

    for recipient in recipients:
        send_email(recipient, subject, todo_html)
