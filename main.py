import email
from email.header import decode_header
import imaplib
from bs4 import BeautifulSoup
import requests
import openai
import os
import time
import re

# メールサーバーに接続する関数
def connect_mail_server(email, password):
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(email, password)
    mail.select("inbox")
    return mail

# 未読のメールIDを取得する関数
def get_unread_mail_ids(mail):
    _, data = mail.search(None, "UNSEEN")
    mail_ids = data[0].split()
    return mail_ids

# BeautifulSoupオブジェクトから本文とURLを抽出する関数
def get_article_content(soup):
    text = ""
    urls = []
    for element in soup.find_all(["h1", "h3", "p", "a"]):
        if element.name == "a":
            url = element.get("href")
            if url:
                urls.append(url)
        else:
            text += element.get_text(strip=True) + "\n"
    return text, urls

# メールを処理し、本文と件名を取得する関数
def process_mail(mail_id, mail):
    _, msg_data = mail.fetch(mail_id, "(RFC822)")
    raw_email = msg_data[0][1]
    raw_mail = email.message_from_bytes(raw_email)

    subject = decode_header(raw_mail["Subject"])[0][0]
    if isinstance(subject, bytes):
        decoded_subject = subject.decode()
    else:
        decoded_subject = subject

    if raw_mail.is_multipart():
        for part in raw_mail.walk():
            if part.get_content_type() == "text/html":
                html_content = part.get_payload(decode=True).decode()
                soup = BeautifulSoup(html_content, "html.parser")
                articles = soup.find_all("h3")
                return articles, decoded_subject

# テキストを要約する関数
def summarize_text(text):
    print(f"Summarizing the following text: {text}")  
    response_summary = openai.ChatCompletion.create(
        model="gpt-3.5-turbo-16k",
        messages=[
            {"role": "system", "content": "You are an assistant who summarizes news articles in Japanese into about 200 characters. You can generate interesting sentences."},
            {"role": "user", "content": f"Here's a news article: {text}. Can you summarize it for me?"},
        ],
        max_tokens=300
    )
    summary = response_summary['choices'][0]['message']['content']
    return summary

# Discordにメッセージを送信する関数
def send_discord_message(webhook_url, content, max_retries=3, retry_delay=5):
    chunks = []
    current_chunk = ""
    for sentence in content.split("."):
        if len(current_chunk) + len(sentence) + 1 > 1999:
            chunks.append(current_chunk)
            current_chunk = sentence
        else:
            current_chunk += "." if current_chunk else ""
            current_chunk += sentence
    if current_chunk:
        chunks.append(current_chunk)

    for chunk in chunks:
        if isinstance(chunk, bytes):
            chunk = chunk.decode('utf-8')

        data = {"content": chunk}
        retries = 0

        while retries <= max_retries:
            response = requests.post(webhook_url, json=data)
            if response.status_code == 204:
                break
            elif response.status_code == 429:
                delay = int(response.headers['Retry-After'])
                time.sleep(delay)
                retries += 1
            else:
                retries += 1
                if retries < max_retries:
                    time.sleep(retry_delay)

# メイン関数
def main():
    email = os.environ["EMAIL"]
    password = os.environ["PASSWORD"]
    webhook_url = os.environ["WEBHOOK_URL"]
    openai.api_key = os.environ["OPENAI_KEY"]

    # メールサーバーに接続
    mail = connect_mail_server(email, password)
    # 未読のメールIDを取得
    mail_ids = get_unread_mail_ids(mail)

    if len(mail_ids) == 0:
        print("No unread mails found. Skipping Discord message sending.")
    else:
        for mail_id in mail_ids:
            # メールを処理し、記事と件名を取得
            articles, decoded_subject = process_mail(mail_id, mail)
            
            formatted_messages = []
            for article in articles:
                # 記事から本文とURLを抽出
                text, urls = get_article_content(article)
                # 本文を要約
                summary = summarize_text(text)

                # URLをフォーマットに合わせて整形
                formatted_urls = "\n".join([f"🔗URL: {url}" for url in urls])
                # メッセージをフォーマットに合わせて整形
                message = f"**Subject: {decoded_subject}**\n\n⌐◨-◨ ⌐◨-◨ ⌐◨-◨ ⌐◨-◨ ⌐◨-◨ ⌐◨-◨\n\n📘 {decoded_subject}\n・{summary}\n{formatted_urls}"
                formatted_messages.append(message)

            # 全てのメッセージを結合
            formatted_output = "\n".join(formatted_messages)
            # Discordにメッセージを送信
            send_discord_message(webhook_url, formatted_output)

if __name__ == "__main__":
    main()
