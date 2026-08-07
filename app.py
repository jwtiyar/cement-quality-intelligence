import os
import uvicorn

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from routes import router
from state import reload_from_csv


app = FastAPI(title="Cement Quality Intelligence")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DASHBOARD_DIR = os.path.join(BASE_DIR, "dashboard")


@app.middleware("http")
async def add_no_cache_header(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.get("/")
def index():
    return FileResponse(os.path.join(DASHBOARD_DIR, "index.html"))


app.include_router(router)

# Load CSV + retrain models on every process start (live data workflow)
reload_from_csv()

app.mount("/", StaticFiles(directory=DASHBOARD_DIR), name="dashboard")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8500)
