from fastapi import FastAPI
from dotenv import load_dotenv

load_dotenv()

from backend.server.ws_server import router as ws_router

app = FastAPI(title="System Caretaker Backend")

app.include_router(ws_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)
