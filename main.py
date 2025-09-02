from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from datetime import datetime
import os, json

# Firebase
import firebase_admin
from firebase_admin import credentials, firestore, messaging

app = FastAPI()

# ===== مفاتيح البيئة =====
INBOUND_API_KEY = os.getenv("INBOUND_API_KEY", "SUPPORT_KEY_2025")

# خدمة Firebase: نقرأ JSON من متغيّر بيئة (Render) أو من ملف محلي
creds_json = os.getenv("FIREBASE_CREDENTIALS_JSON")  # مفضّل على Render
if creds_json:
    cred = credentials.Certificate(json.loads(creds_json))
else:
    # للاستخدام المحلي فقط إذا عندك ملف بجنب main.py
    cred = credentials.Certificate("serviceAccountKey.json")

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()


# ===== نموذج البيانات =====
class GmailPayload(BaseModel):
    from_: str | None = None
    subject: str
    bodyPlain: str | None = None
    bodyHtml: str | None = None
    date: str
    msgId: str
    threadId: str
    attachments: list[dict] = []


# ===== المسار الذي يستقبل البريد =====
@app.post("/inbound/email")
async def receive_email(request: Request):
    # حماية بسيطة بالمفتاح
    if request.headers.get("x-api-key") != INBOUND_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    data = await request.json()
    msg = GmailPayload(**{
        "from_": data.get("from"),
        "subject": data.get("subject", ""),
        "bodyPlain": data.get("bodyPlain", ""),
        "bodyHtml": data.get("bodyHtml", ""),
        "date": data.get("date", ""),
        "msgId": data.get("msgId", ""),
        "threadId": data.get("threadId", ""),
        "attachments": data.get("attachments", []),
    })

    # طباعة للمتابعة
    print(f"📩 Received email from: {msg.from_}")
    print(f"Subject: {msg.subject}")
    print(f"Body: {msg.bodyPlain}")
    print(f"Date: {msg.date}")
    print(f"Attachments: {[a.get('name') for a in msg.attachments]}")

    # ===== تخزين التذكرة في Firestore =====
    ticket = {
        "from": msg.from_,
        "subject": msg.subject,
        "body": msg.bodyPlain,
        "html": msg.bodyHtml,
        "date": msg.date,
        "threadId": msg.threadId,
        "status": "new",  # new | in_progress | resolved | rejected
        "createdAt": datetime.utcnow().isoformat() + "Z"
    }
    db.collection("tickets").document(msg.msgId).set(ticket)

    # ===== إشعار FCM (لكل من اشترك بموضوع all) =====
    try:
        messaging.send(messaging.Message(
            notification=messaging.Notification(
                title=f"📩 New ticket: {msg.subject}",
                body=(msg.bodyPlain or "")[:120]
            ),
            topic="all"
        ))
        print("✅ FCM notification sent.")
    except Exception as e:
        print(f"⚠️ FCM error: {e}")

    return {"status": "stored & notified"}
