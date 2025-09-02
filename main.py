from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
import os

app = FastAPI()

INBOUND_API_KEY = os.getenv("INBOUND_API_KEY", "SUPPORT_KEY_2025")

class GmailPayload(BaseModel):
    from_: str | None = None
    subject: str
    bodyPlain: str | None = None
    bodyHtml: str | None = None
    date: str
    msgId: str
    threadId: str
    attachments: list[dict] = []

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
    print(f"Body: {msg.bodyPlain}")
    print(f"Date: {msg.date}")
    print(f"Attachments: {[a['name'] for a in msg.attachments]}")

    return {"status": "received"}
