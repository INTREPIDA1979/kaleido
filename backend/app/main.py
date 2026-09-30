import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.routers import chat, upload, agents, tts, admin

import warnings
import logging

# 1. Python標準の警告をすべて無視
warnings.filterwarnings("ignore")

# 2. Vertex AIやGoogle Cloud特有の警告ログを強制的にエラーレベルのみに制限
os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GLOG_minloglevel"] = "2"
logging.getLogger("google").setLevel(logging.ERROR)
logging.getLogger("vertexai").setLevel(logging.ERROR)

app = FastAPI(title="Kaleido API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.include_router(chat.router, prefix="/api/v1")
app.include_router(upload.router, prefix="/api/v1")
app.include_router(agents.router, prefix="/api/v1")
app.include_router(tts.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")

@app.get("/health")
def health_check():
    return {"status": "ok", "project": "Kaleido"}