from fastapi import FastAPI, HTTPException, Request, Depends
from pydantic import BaseModel
import redis
import json
import uuid
from dotenv import load_dotenv

load_dotenv()

# GET api token
def get_api_token():
    try:
        with open("/run/secrets/api_token", "r") as secret_file:
            return secret_file.read().strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading secret: {e}")

API_TOKEN = get_api_token()

app = FastAPI()

# Connect to Redis
redis_client = redis.Redis(host="redis", port=6379, db=0)


class DownloadRequest(BaseModel):
    url: str
    chat_id: str


async def verify_token(request: Request):
    token = request.headers.get("Authorization")
    if not token or token != f"Bearer {API_TOKEN}":
        raise HTTPException(status_code=403, detail="Forbidden")


@app.post("/download", dependencies=[Depends(verify_token)])
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