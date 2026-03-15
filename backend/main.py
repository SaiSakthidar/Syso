from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
import os

load_dotenv()

from backend.server.ws_server import router as ws_router
from backend.server.auth import router as auth_router

app = FastAPI(title="System Caretaker Backend")

# Essential for Authlib OAuth session management
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "syso-secret-123"))

app.include_router(ws_router)
app.include_router(auth_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
