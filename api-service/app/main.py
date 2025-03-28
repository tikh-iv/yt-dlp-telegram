from fastapi import FastAPI, HTTPException, Request, Depends
from pydantic import BaseModel
import redis
import json
import uuid
import os
from dotenv import load_dotenv
from __future__ import annotations

load_dotenv()
API_TOKEN = os.getenv("API_TOKEN")

app = FastAPI()

# Connect to Redis
redis_client = redis.Redis(host="redis", port=6379, db=0)

# GET api token
def get_api_token():
    try:
        with open("/run/secrets/api_token", "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None

API_TOKEN = get_api_token()


class DownloadRequest(BaseModel):
    url: str
    chat_id: str


async def verify_token(request: Request):
    token = request.headers.get("Authorization")
    if not token or token != f"Bearer {API_TOKEN}":
        raise HTTPException(status_code=403, detail="Forbidden")


@app.post("/download/", dependencies=[Depends(verify_token)])
async def request_download(request: DownloadRequest):
    """ Get link and starts to download """""
    task_id = str(uuid.uuid4())
    task = {
        "task_id": task_id,
        "url": request.url,
        "chat_id": request.chat_id
    }

    # Put task in queue
    redis_client.rpush("download_tasks", json.dumps(task))

    return {"message": "Task is created", "task_id": task_id}