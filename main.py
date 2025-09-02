from fastapi import FastAPI, Request, HTTPException, Form, UploadFile, File, Header
from typing import List
from pydantic import BaseModel
from datetime import datetime
import os, json

# Firebase
import firebase_admin
from firebase_admin import credentials, firestore, messaging, storage

app = FastAPI()

# ===== مفاتيح البيئة =====
INBOUND_API_KEY = os.getenv("INBOUND_API_KEY", "SUPPORT_KEY_2025")
FIREBASE_STORAGE_BUCKET = os.getenv("FIREBASE_STORAGE_BUCKET", "")  # ex: poultry-project-2ba07.appspot.com

# ===== تهيئة Firebase =====
creds_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
if creds_json:
    cred = credentials.Certificate(json.loads(creds_json))
else:
    cred = credentials.Certificate("serviceAccountKey.json")  # للاستخدام المحلي فقط

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred, {
        "storageBucket": FIREBASE_STORAGE_BUCKET or None
    })

db = firestore.client()
bucket = storage.bucket(FIREBASE_STORAGE_BUCKET) if FIREBASE_STORAGE_BUCKET else None


# ===== نموذج البريد القادم من Gmail =====
class GmailPayload(BaseModel):
    from_: str | None = None
    subject: str
    bodyPlain: str | None = None
    bodyHtml: str | None = None
    date: str
    msgId: str
    threadId: str
    attachments: list[dict] = []


# ===== Gmail → Firestore =====
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

    print(f"📩 Email from: {msg.from_} | Subject: {msg.subject}")

    db.collection("tickets").document(msg.msgId).set({
        "type": "email",
        "from": msg.from_,
        "subject": msg.subject,
        "body": msg.bodyPlain,
        "html": msg.bodyHtml,
        "date": msg.date,
        "threadId": msg.threadId,
        "status": "new",
        "attachments": msg.attachments,
        "createdAt": datetime.utcnow().isoformat() + "Z"
    })

    try:
        messaging.send(messaging.Message(
            notification=messaging.Notification(
                title=f"📩 New ticket: {msg.subject}",
                body=(msg.bodyPlain or "")[:120]
            ),
            topic="all"
        ))
    except Exception as e:
        print("⚠️ FCM error:", e)

    return {"status": "stored & notified"}


# ===== Flutter → Firestore + Storage =====
@app.post("/tickets")
async def create_ticket(
    title: str = Form(...),
    description: str = Form(...),
    userId: str = Form(...),
    userEmail: str = Form(...),
    system: str = Form("poultry"),
    attachments: List[UploadFile] = File([]),
    x_api_key: str = Header(None)
):
    if x_api_key != INBOUND_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    doc_ref = db.collection("tickets").document()
    ticket_id = doc_ref.id

    files_meta = []
    if bucket and attachments:
        for f in attachments:
            fname = f.filename or "file"
            blob_path = f"tickets/{ticket_id}/{fname}"
            blob = bucket.blob(blob_path)
            blob.upload_from_file(f.file, content_type=f.content_type)
            try:
                blob.make_public()
                url = blob.public_url
            except Exception:
                url = blob_path
            files_meta.append({
                "name": fname,
                "contentType": f.content_type,
                "url": url,
                "path": blob_path
            })
            f.file.close()

    data = {
        "type": "app",
        "title": title,
        "description": description,
        "userId": userId,
        "userEmail": userEmail,
        "system": system,
        "attachments": files_meta,
        "status": "submitted",
        "createdAt": datetime.utcnow().isoformat() + "Z"
    }
    doc_ref.set(data)

    try:
        messaging.send(messaging.Message(
            notification=messaging.Notification(
                title="🧩 New app ticket",
                body=title
            ),
            topic="all"
        ))
    except Exception as e:
        print("⚠️ FCM error:", e)

    return {"ok": True, "ticketId": ticket_id, "files": files_meta}


# ===== Health Check =====
@app.get("/health")
def health():
    return {"ok": True}
