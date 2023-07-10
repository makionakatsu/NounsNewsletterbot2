import email
from email.header import decode_header
import imaplib
from bs4 import BeautifulSoup
import requests
import openai
import os
import time

# メールサーバーに接続する関数
def connect_mail_server(email, password):
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(email, password)
    mail.select("inbox")
    return mail

# 未読メールのIDを取得する関数
def get_unread_mail_ids(mail):
    _, data = mail.search(None, "UNSEEN")
    mail_ids = data[0].split()
    return mail_ids

# HTMLからテキストを抽出する関数
def get_text(soup):
    text = ""
    for element in soup.find_all(["h1", "h3", "p", "a"]):
        if element.name == "a":
            url = element.get("href")
            if url:
                text += f"URL: {url}\n"
        else:
            text += element.get_text(strip=True)
    return text

# メールを処理し、テキストと件名を取得する関数
def process_mail(mail_id, mail):
    _, msg_data = mail.fetch(mail_id, "(RFC822)")
    raw_email = msg_data[0][1]
    msg = email.message_from_bytes(raw_email)

    decoded_subject_string = decode_subject(msg["subject"])

    text = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                text += part.get_payload(decode=True).decode()
            elif part.get_content_type() == "text/html":
                html_content = part.get_payload(decode=True).decode()
                soup = BeautifulSoup(html_content, "html.parser")
                text += get_text(soup)
    else:
        text = msg.get_payload(decode=True).decode()

    return text, decoded_subject_string

# 件名をデコードする関数
def decode_subject(subject):
    decoded_subject = decode_header(subject)
    decoded_subject_string = ""
    for item in decoded_subject:
        if item[1]:
            decoded_subject_string += item[0].decode(item[1])
        else:
            decoded_subject_string += item[0]
    return decoded_subject_string

# テキストからURLを抽出する関数
def extract_urls_from_text(text):
    soup = BeautifulSoup(text, "html.parser")
    urls = [a['href'] for a in soup.find_all('a', href=True)]
    return urls

# テキストを要約する関数
def summarize_text(text):
    response_summary = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are an assistant who summarizes news articles into about 200 characters. You can generate interesting sentences."},
            {"role": "user", "content": f"Here's a news article: {text}. Can you summarize it for me?"},
        ],
        max_tokens=200
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
                print(f"Rate limit hit. Waiting for {delay} seconds.")
                time.sleep(delay)
                retries += 1
            else:
                print(f"Failed to send message (attempt {retries + 1}): {response.text}")
                if retries < max_retries:
                    time.sleep(retry_delay)
                    retries += 1
                else:
                    print(f"Giving up after {max_retries} attempts")
                    return

        time.sleep(1)

# メインの処理
def main():
    email = os.environ["EMAIL"]
    password = os.environ["PASSWORD"]
    webhook_url = os.environ["WEBHOOK_URL"]
    openai.api_key = os.environ["OPENAI_KEY"]

    mail = connect_mail_server(email, password)
    mail_ids = get_unread_mail_ids(mail)

    if len(mail_ids) == 0:
        print("No unread mails found. Skipping Discord message sending.")
    else:
        for mail_id in mail_ids:
            text, decoded_subject_string = process_mail(mail_id, mail)
            urls = extract_urls_from_text(text)
            
            # メールの内容をh3タグで分割し、各記事を処理
            articles = text.split("<h3>")
            for article in articles:
                summary = summarize_text(article)
                urls = extract_urls_from_text(article)
                
                formatted_messages = []
                for url in urls:
                    message = f"⌐◨-◨ ⌐◨-◨ ⌐◨-◨ ⌐◨-◨ ⌐◨-◨ ⌐◨-◨\n\n📘 {decoded_subject_string}\n・{summary}\n🔗URL: {url}\n\n⌐◨-◨ ⌐◨-◨ ⌐◨-◨ ⌐◨-◨ ⌐◨-◨ ⌐◨-◨"
