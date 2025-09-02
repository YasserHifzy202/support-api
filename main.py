from fastapi import FastAPI, Request, HTTPException, UploadFile, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from datetime import datetime
from typing import List
import os, json, uuid

# Firebase
import firebase_admin
from firebase_admin import credentials, firestore, messaging, storage

app = FastAPI()

# ===== مفاتيح البيئة =====
INBOUND_API_KEY = os.getenv("INBOUND_API_KEY", "SUPPORT_KEY_2025")
FIREBASE_STORAGE_BUCKET = os.getenv("FIREBASE_STORAGE_BUCKET")

# خدمة Firebase: نقرأ JSON من متغيّر بيئة (Render) أو من ملف محلي
creds_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
if creds_json:
    cred = credentials.Certificate(json.loads(creds_json))
else:
    cred = credentials.Certificate("serviceAccountKey.json")

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred, {
        "storageBucket": FIREBASE_STORAGE_BUCKET
    })

db = firestore.client()
bucket = storage.bucket(FIREBASE_STORAGE_BUCKET)


# ===== نموذج بيانات البريد =====
class GmailPayload(BaseModel):
    from_: str | None = None
    subject: str
    bodyPlain: str | None = None
    bodyHtml: str | None = None
    date: str
    msgId: str
    threadId: str
    attachments: list[dict] = []


# ===== استقبال البريد (Apps Script) =====
@app.post("/inbound/email")
async def receive_email(request: Request):
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

    print(f"📩 Received email from: {msg.from_}")
    print(f"Subject: {msg.subject}")

    ticket = {
        "from": msg.from_,
        "subject": msg.subject,
        "body": msg.bodyPlain,
        "html": msg.bodyHtml,
        "date": msg.date,
        "threadId": msg.threadId,
        "status": "new",
        "createdAt": datetime.utcnow().isoformat() + "Z"
    }
    db.collection("tickets").document(msg.msgId).set(ticket)

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


# ===== إنشاء تذكرة من التطبيق (مع مرفقات) =====
@app.post("/tickets")
async def create_ticket(
    title: str = Form(...),
    description: str = Form(...),
    userId: str = Form(...),
    userEmail: str = Form(...),
    system: str = Form(...),
    attachments: List[UploadFile] = []
):
    ticket_id = str(uuid.uuid4())
    uploaded_files = []

    # رفع الملفات إلى Firebase Storage
    for f in attachments:
        try:
            blob = bucket.blob(f"tickets/{ticket_id}/{f.filename}")
            blob.upload_from_file(f.file, content_type=f.content_type)
            uploaded_files.append({
                "name": f.filename,
                "url": blob.public_url
            })
        except Exception as e:
            print(f"⚠️ Upload error for {f.filename}: {e}")

    ticket = {
        "title": title,
        "description": description,
        "userId": userId,
        "userEmail": userEmail,
        "system": system,
        "status": "submitted",
        "attachments": uploaded_files,
        "createdAt": datetime.utcnow().isoformat() + "Z",
        "type": "app"
    }
    db.collection("tickets").document(ticket_id).set(ticket)

    return JSONResponse({"status": "ticket stored", "id": ticket_id, "files": uploaded_files})
