import re
from typing import Optional, TypedDict

import pandas as pd
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph
from dotenv import load_dotenv
load_dotenv()

from sandbox import run_in_sandbox

MAX_RETRIES = 3
llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0)

CODER_SYSTEM = """You are a data analyst who answers questions by writing Python.

Rules:
- The data is a CSV at /data/input.csv. Load it with pandas.
- Use only pandas, numpy and matplotlib.
- Print the final answer with print(). Print small result tables (up to ~30 rows) in full. Never use .head() on aggregated results, because the answer is written only from what you print. Only truncate genuinely large tables.
- If a chart helps, save it with plt.savefig('/output/chart.png', bbox_inches='tight').
- Use the exact column names from the schema. Do not invent columns.
- Respond with ONLY one ```python code block. No explanation.
- Only use columns that exist in the schema. If the question needs data that is not in the CSV (for example cost or profit when there is no such column), do NOT approximate it or invent a proxy. Print exactly: CANNOT_ANSWER: <what is missing>
"""


class State(TypedDict):
    question: str
    csv_path: str
    schema: str
    code: str
    stdout: str
    error: Optional[str]
    retries: int
    chart_path: Optional[str]
    answer: str


def extract_code(text: str) -> str:
    match = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    return (match.group(1) if match else text).strip()


# ---------- nodes ----------

def inspect_node(state: State) -> dict:
    df = pd.read_csv(state["csv_path"])
    schema = (
        f"Rows: {len(df)}\n"
        f"Columns and dtypes:\n{df.dtypes.to_string()}\n\n"
        f"Sample rows:\n{df.head(5).to_string()}"
    )
    return {"schema": schema, "retries": 0, "error": None, "chart_path": None}


def coder_node(state: State) -> dict:
    prompt = f"Schema:\n{state['schema']}\n\nQuestion: {state['question']}"
    if state.get("error"):
        prompt += (
            f"\n\nYour previous code:\n```python\n{state['code']}\n```\n"
            f"It failed with:\n{state['error']}\n"
            "Fix the problem and return the full corrected script."
        )
    resp = llm.invoke([("system", CODER_SYSTEM), ("human", prompt)])
    return {"code": extract_code(resp.content)}


def executor_node(state: State) -> dict:
    result = run_in_sandbox(state["code"], state["csv_path"])
    if result["ok"]:
        return {"stdout": result["stdout"], "error": None, "chart_path": result["chart_path"]}
    return {"error": result["stderr"], "retries": state["retries"] + 1}


def responder_node(state: State) -> dict:
    prompt = (
        f"Question: {state['question']}\n\n"
        f"Code output:\n{state['stdout']}\n\n"
        "If the code output starts with CANNOT_ANSWER, tell the user this cannot be answered from the data and say what is missing. Do not guess. "
        "Answer the question in 2-4 plain-English sentences using only this output. "
"Do not add currency symbols or units that are not in the data."
    )
    return {"answer": llm.invoke(prompt).content}


def give_up_node(state: State) -> dict:
    return {"answer": f"I couldn't solve this after {MAX_RETRIES} attempts. Last error:\n{state['error']}"}


# ---------- routing ----------

def route_after_exec(state: State) -> str:
    if state["error"] is None:
        return "respond"
    if state["retries"] >= MAX_RETRIES:
        return "give_up"
    return "coder"


# ---------- graph ----------

def build_graph():
    g = StateGraph(State)
    g.add_node("inspect", inspect_node)
    g.add_node("coder", coder_node)
    g.add_node("executor", executor_node)
    g.add_node("respond", responder_node)
    g.add_node("give_up", give_up_node)

    g.set_entry_point("inspect")
    g.add_edge("inspect", "coder")
    g.add_edge("coder", "executor")
    g.add_conditional_edges(
        "executor",
        route_after_exec,
        {"respond": "respond", "give_up": "give_up", "coder": "coder"},
    )
    g.add_edge("respond", END)
    g.add_edge("give_up", END)
    return g.compile()


graph = build_graph()


def run_agent(question: str, csv_path: str) -> State:
    return graph.invoke({"question": question, "csv_path": csv_path})


if __name__ == "__main__":
    import sys

    out = run_agent(sys.argv[2], sys.argv[1])
    print("CODE:\n", out["code"])
    print("\nANSWER:\n", out["answer"])
    print("\nCHART:", out.get("chart_path"))
