# 🐼📦 Sandboxed CSV Analyst

> Ask questions about a CSV in plain English. An LLM writes pandas code, the code runs inside an **isolated Docker sandbox**, and if it crashes, the error is fed back to the model so it can fix itself.



---

## ✨ What it does

Upload a CSV, ask something like *"Which city has the highest revenue from Delivered orders, after applying the discount?"*, and get back:

- 💬 a plain-English answer
- 📊 a chart, when the question asks for one
- 🧾 the exact Python code that produced the answer (so you can verify it)

It also **refuses to guess**. If the question needs data that isn't in the file (for example, profit margin with no cost column), it says so instead of inventing a number.

---

## 🧠 How it works

```
 question + CSV
       │
       ▼
 🔍 Inspect schema        column names, dtypes, 5 sample rows (the LLM never sees the full file)
       │
       ▼
 ✍️  Coder (LLM)          writes pandas code
       │
       ▼
 📦 Docker sandbox        runs the code in a throwaway container
       │
       ├── ❌ error ──→ traceback goes back to the Coder (max 3 retries)
       │
       ▼
 💬 Responder (LLM)       turns the printed output into a short answer (+ chart)
```

Built as a **LangGraph** state machine: five nodes and one conditional edge that decides between *respond*, *retry*, or *give up*.

---

## 🔒 The sandbox

LLM-generated code is **untrusted input**, so it never runs on the host. Every execution happens in a fresh container:

| Flag | Why it's there |
|------|----------------|
| `--network none` | generated code can't call out to anything |
| `--memory 256m`, `--cpus 0.5` | a runaway script can't take down the machine |
| `--pids-limit 64` | blocks fork bombs |
| `--read-only` + `--tmpfs /tmp` | the container's filesystem can't be modified |
| CSV mounted `:ro` | the code can't change your data |
| non-root user | no elevated privileges inside the container |
| 25 s timeout + `docker kill` | infinite loops get killed (killing only the Docker client would leave the container running) |
| `--rm` | the container disappears after every run |

> ⚠️ This is **isolation, not a hardened production system**
---

## 🧪 Evaluation

The repo includes a small eval harness (`eval_agent.py`): **11 questions with known answers**, graded automatically. Each test lists the values that must appear in the answer, and the harness reports accuracy and average retries.

| Run | Result |
|-----|--------|
| First run (1× each) | 9 / 11 |
| After fixes (3× each) | **32 / 33** |

What the eval caught along the way:

- 🐛 **A hallucination.** Asked for the *profit margin* on a dataset with no cost column, the agent confidently answered **96.4%**. Fix: an explicit `CANNOT_ANSWER` path in the prompt. After that, the unanswerable test passed 3/3.
- 🐛 **A checker bug.** The model sometimes emits Unicode hyphens (`2025‑08`), which a plain-text match missed. Fixed by normalizing characters before comparing.

I also spot-checked a **second, messier dataset** (`sample_orders.csv`: different column names, blank values, no revenue column, dates to parse) including a refusal question, and a monthly bar chart.

Run it yourself: [see below](#-run-the-eval).

---

## 🚀 Getting started

### Prerequisites

- 🐍 Python 3.10+
- 🐳 [Docker Desktop](https://www.docker.com/products/docker-desktop/) (running)
- 🔑 A free [Groq API key](https://console.groq.com)

### 1. Clone the repo

```bash
git clone https://github.com/shshy911/Sandboxed-CSV-Analyst.git
cd Sandboxed-CSV-Analyst
```

### 2. Build the sandbox image

```bash
docker build -t analyst-sandbox .
```

> The image name must stay `analyst-sandbox` (it's set as `IMAGE` in `sandbox.py`).

### 3. Create a virtual environment and install dependencies

**Windows (PowerShell):**
```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Add your API key

Copy `.env.example` to `.env` and put your key in it:

```
GROQ_API_KEY=your_key_here
```

> 🔐 `.env` is git-ignored. Never commit your key.

### 5. Pick a model

`agent.py` uses `openai/gpt-oss-120b` on Groq. Model availability changes, so if you get a `model_not_found` error, list the models your key can use:

```bash
python -c "from dotenv import load_dotenv; load_dotenv(); from groq import Groq; [print(m.id) for m in Groq().models.list().data]"
```

Then set the model name on the `llm = ChatGroq(...)` line in `agent.py`.

### 6. Run the web app

```bash
uvicorn main:app --reload
```

Open **http://localhost:8000**, upload a CSV, ask a question, and click **Analyze**. ⏱️ Each question takes roughly 10-30 seconds.

> Open the app through `localhost:8000`, not by double-clicking `index.html`. The page calls `/analyze` on the same server.

### Or use the CLI

```bash
python agent.py sample_sales.csv "Which region has the most returns?"
```

### 🧮 Run the eval

```bash
python eval_agent.py            # each question once
python eval_agent.py --runs 3   # each question 3×, since LLM output varies
```

Failed answers are written to `eval_results.json` so you can inspect them.

---

## 🎯 Try these questions

**`sample_sales.csv`** (48 rows: monthly sales by region)

| Question | Expected |
|----------|----------|
| Which month had the biggest drop in total revenue vs the previous month? | **August 2025** (−65,587) |
| Which region has the most returns in total? | **South** (197) |
| Plot monthly revenue as one line per region, marking each region's lowest point | four lines, all dipping in August |
| What was the profit margin in March? | should say it **can't be computed** |

**`sample_orders.csv`** (150 e-commerce orders, with missing values)

| Question | Expected |
|----------|----------|
| Which category earns the most gross revenue (qty × unit_price)? | **Electronics** (952,290) |
| Which city has the highest revenue from Delivered orders, after applying discount_pct (missing = 0)? | **Mumbai** (~383,318) |
| Plot total gross revenue per month as a bar chart | six bars, **August** tallest |
| What is the average age of the customers? | should say it **can't be answered** |

---

## 🗂️ Project structure

```
├── agent.py          # LangGraph agent: inspect → code → execute → respond
├── sandbox.py        # Docker executor with the isolation flags
├── main.py           # FastAPI app (serves the UI + POST /analyze)
├── index.html        # single-file frontend
├── eval_agent.py     # eval harness (11 questions, --runs N)
├── Dockerfile        # sandbox image (python + pandas, numpy, matplotlib)
├── sample_sales.csv
├── sample_orders.csv
├── requirements.txt
└── .env.example
```

## 🧰 Tech stack

**LangGraph** · **LangChain (Groq)** · **FastAPI** · **Docker** · **pandas / matplotlib** · plain HTML/JS frontend

---

<p align="center">Built as a learning project on agent design, sandboxing, and evaluation. ⭐ if you found it useful!</p>
