import base64
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse

from agent import run_agent

BASE_DIR = Path(__file__).parent
app = FastAPI(title="Data Analyst Agent")


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "index.html")


@app.post("/analyze")
async def analyze(file: UploadFile = File(...), question: str = Form(...)):
    tmp = Path(tempfile.mkdtemp()) / "input.csv"
    tmp.write_bytes(await file.read())

    result = run_agent(question, str(tmp))

    chart_b64 = None
    if result.get("chart_path"):
        chart_b64 = base64.b64encode(Path(result["chart_path"]).read_bytes()).decode()

    return {
        "answer": result["answer"],
        "code": result.get("code"),
        "retries": result.get("retries", 0),
        "chart_base64_png": chart_b64,
    }
