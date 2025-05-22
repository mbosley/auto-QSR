# Qualitative Safety Report (QSR) Demo

**Implementation Plan – Portable, Local‑First Edition**
*Version 1.1 — 22 May 2025*

---

## 0 · Objective

Provide a *turn‑key* repository + Docker image that anyone can run **locally** (no cloud credentials) to demonstrate an end‑to‑end “Qualitative Safety Report” pipeline:

1. Generate synthetic multi‑modal usage events (Gemini chat, Imagen image‑gen, Search snippets).
2. Store events in **Parquet → DuckDB**.
3. Run **platform‑level LLM agents** that summarise 24 h of activity into *Platform Safety Summaries (PSS)*.
4. Feed those summaries to an **aggregate LLM agent** that produces a *Qualitative Safety Report (QSR)* with
   • Narrative text  • Risk vector (JSON)  • Macro‑patterns  • Recommended moderation tier.
5. Persist QSRs to DuckDB and visualise them with a **Streamlit** dashboard.
6. Package everything in a **Dockerfile** so reviewers launch with one command.

Only external requirement: an **LLM API key** (`LLM_API_KEY`) for OpenAI GPT‑4o or Google Gemini.

---

## 1 · Technology Stack

| Layer        | Tool                                         | Rationale                                   |
| ------------ | -------------------------------------------- | ------------------------------------------- |
| Workflow     | `make`                                       | Simple, declarative dependencies            |
| Local DB     | `DuckDB ≥0.10`                               | Zero‑config OLAP, supports Parquet natively |
| Column files | `Parquet / Arrow`                            | Fast, portable                              |
| LLM SDK      | `openai ≥1.28` or `google‑generativeai ≥0.4` | Model‑agnostic, single HTTP call            |
| Dashboard    | `Streamlit ≥1.34`                            | Instant web UI                              |
| Packaging    | `Docker ≥24`                                 | Reproducible runtime                        |
| Tests        | `pytest`                                     | CI sanity check                             |

---

## 2 · Prerequisites (non‑Docker path)

```bash
# Clone
git clone https://github.com/<ORG>/qsr-local.git && cd qsr-local

# Python 3.11 via pyenv (skip if installed)
pyenv install 3.11.9 && pyenv local 3.11.9

# Poetry env + deps
pip install poetry
poetry install --no-root
poetry shell

# LLM key (OpenAI shown here)
export LLM_API_KEY="sk‑…"
```

---

## 3 · Repository Layout

```
qsr-local/
├─ README.md              ← Quick‑start
├─ Makefile               ← One‑liner targets
├─ Dockerfile/.dockerignore
├─ sql/                   ← DuckDB SQL (one per platform)
│  ├─ gemini.sql
│  ├─ imagen.sql
│  └─ search.sql
├─ prompts/
│  ├─ platform_prompt.txt ← FULL prompt for platform agents
│  └─ aggregate_prompt.txt← FULL prompt for aggregate agent
├─ synthetic/generate.py  ← Fake event generator
├─ src/                   ← Python helpers
│  ├─ run_sql_duckdb.py
│  ├─ platform_agent.py
│  ├─ aggregate_agent.py
│  └─ __init__.py
├─ dashboard/ui.py        ← Streamlit reviewer console
├─ tests/test_pipeline.py ← CI smoke test
└─ data/ (gitignored)     ← Parquet + qsr.duckdb at runtime
```

---

## 4 · Synthetic Data Generator (`synthetic/generate.py`)

```python
import pandas as pd, random, datetime as dt, pyarrow.parquet as pq, pyarrow as pa, pathlib

def sample(surface: str, n: int = 120):
    rng, now = random.Random(42), dt.datetime.utcnow()
    intents = {
        "gemini": ["disable safe‑mode", "how to groom minors", "share extremist meme"],
        "imagen": ["violent deepfake", "csam cartoon", "normal cat pic"],
        "search": ["torrent illegal video", "vegan recipe", "how to scam"]
    }
    rows = [{
        "user_id": "demo_user",
        "ts": now ­ dt.timedelta(minutes=rng.randint(0, 1440)),
        "text": rng.choice(intents[surface]),
        "policy_flag": rng.choice(["child_safety", "violence", "none", "extremism"])
    } for _ in range(n)]
    return pd.DataFrame(rows)

pathlib.Path("data").mkdir(exist_ok=True)
for s in ("gemini", "imagen", "search"):
    pq.write_table(pa.Table.from_pandas(sample(s)), f"data/{s}.parquet")
print("✓ Synthetic events saved → data/*.parquet")
```

---

## 5 · SQL Scripts  (`sql/<surface>.sql`)

Example `gemini.sql` (copy / adapt path & table name for others):

```sql
INSTALL parquet; LOAD parquet;
CREATE OR REPLACE TABLE gemini_24h AS
SELECT *
FROM read_parquet('data/gemini.parquet')
WHERE ts BETWEEN now() ­ INTERVAL 1 DAY AND now();
```

---

## 6 · **Full LLM Prompts**

### 6.1 Platform‑Level Prompt (`prompts/platform_prompt.txt`)

```
SYSTEM
You are a **Platform Safety Agent** working for {surface}.  Your mission is to analyse all events
from a *single user* in the last 24 hours and output a concise safety summary.

TASK
1. **Cluster** adjacent events into up to **20 INCIDENTS**.  Two events belong in the same
   incident if they share topic *and* are ≤15 minutes apart.
2. For each incident, produce the following JSON object:
   {
     "timeframe": "YYYY‑MM‑DD HH:MM–HH:MM UTC",
     "snippet"   : "≤120 char user text or image description",
     "violated_policy": ["child_safety"|"violence"|"extremism"|"scam"|"none"|…],
     "risk_scores": {
        "CSAM"     : 0‑1,
        "violence" : 0‑1,
        "self_harm": 0‑1,
        "disinfo"  : 0‑1,
        "scam"     : 0‑1,
        "hateful"  : 0‑1
     },
     "confidence": 0‑1
   }
3. After listing incidents, write **two short paragraphs** (≤160 words total) that summarise – in
   plain English – the user’s behaviour and notable safety concerns.

FORMAT
Return valid **JSON** with exactly two top‑level keys:
  "incidents": [ … ],
  "summary"  : "…"
Do *not* wrap in Markdown.
```

### 6.2 Aggregate Prompt (`prompts/aggregate_prompt.txt`)

```
SYSTEM
You are the **Senior Safety Synthesiser**.  You receive up to four JSON blobs, each produced by a
Platform Safety Agent (Gemini, Imagen, Search, Bard).  Your job is to fuse them into a single
**Qualitative Safety Report (QSR)**.

TASK
1. Merge incidents across platforms.  Remove duplicates and order chronologically.
2. Compute **risk_vector** where each dimension = *max* risk score among all incidents.
3. Detect **macro_patterns**, e.g.:
   • "multi‑surface CSAM generation"  • "step‑wise scam funnel"  • "sustained extremist persuasion".
4. Determine **recommended_action.tier**:
     3 → CSAM ≥0.9 OR credible self‑harm plan ≥0.9
     2 → any risk ≥0.6
     1 → any risk ≥0.3
     0 → otherwise
5. Output the following JSON exactly:
{
  "narrative"        : "≤300 words plain English overview…",
  "risk_vector"      : { "CSAM":…, "violence":…, … },
  "macro_patterns"   : [ "string", … ],
  "recommended_action": { "tier": 0‑3, "justification": "short reason" }
}

FORMAT
Return **ONLY** that JSON – no Markdown, no comments.
```

---

## 7 · Python Helpers

The helper scripts — `run_sql_duckdb.py`, `platform_agent.py`, `aggregate_agent.py` — are unchanged from version 1.0; every line is retained in `src/`.

---

## 8 · Streamlit Dashboard (`dashboard/ui.py`)

```python
import streamlit as st, duckdb, pandas as pd, json, pathlib
DB = pathlib.Path("qsr.duckdb")
con = duckdb.connect(DB, read_only=True)
qsr = con.execute("SELECT * FROM qsr_reports ORDER BY report_ts DESC").df()
con.close()

st.set_page_config(page_title="QSR Demo", layout="wide")
st.title("Qualitative Safety Report – Local Demo")
if qsr.empty():
    st.error("Run `make demo` first.")
    st.stop()
row = qsr.iloc[0]
risk = pd.json_normalize(row["risk_vector"]).T.rename(columns={0:"score"})

col1, col2 = st.columns([2,1])
with col1:
    st.subheader("Narrative")
    st.write(row["narrative"])
with col2:
    st.subheader("Risk Vector")
    st.bar_chart(risk)

st.subheader("Macro‑patterns")
st.write(row["macro_patterns"])

st.subheader("Raw JSON")
st.json(json.loads(row["raw_json"]))
```

---

## 9 · Make Targets (`Makefile`)

```
LLM_MODEL ?= gpt-4o-mini
SURFACES  := gemini imagen search

.PHONY: generate extract pss qsr demo clean

generate:
	python synthetic/generate.py

sql_%: sql/%.sql
	python src/run_sql_duckdb.py $<

extract: $(addprefix sql_, $(SURFACES))

%.pss.json: extract
	python src/platform_agent.py --surface $* --out $@

pss: $(addsuffix .pss.json, $(SURFACES))

qsr: pss
	python src/aggregate_agent.py prompts/aggregate_prompt.txt qsr_master.json

demo: generate extract pss qsr
	@echo "✓ Pipeline done →  streamlit run dashboard/ui.py"

clean:
	rm -f *.pss.json qsr_master.json qsr.duckdb
```

---

## 10 · Docker Support

### `Dockerfile`

```Dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir poetry==1.8.2 && \
    poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi

EXPOSE 8501
CMD ["bash", "-c", "make demo && streamlit run dashboard/ui.py --server.headless=true"]
```

### `.dockerignore`

```
.git
__pycache__/
.idea/
*.parquet
*.duckdb
.env
```

### Build & Run

```bash
docker build -t qsr-demo:latest .
docker run -e LLM_API_KEY=sk-… -p 8501:8501 qsr-demo:latest
# visit http://localhost:8501
```

---

## 11 · Testing & CI

* `tests/test_pipeline.py` triggers `make demo` and asserts the QSR JSON contains a valid tier (0‑3).
* GitHub Actions workflow installs Poetry, runs tests, and caches wheels.

---

## 12 · Troubleshooting

| Issue                               | Resolution                                         |
| ----------------------------------- | -------------------------------------------------- |
| `openai.error.AuthenticationError`  | Ensure `LLM_API_KEY` exported (or `-e` in docker). |
| Dashboard says “Run pipeline first” | Execute `make demo` inside same env/container.     |
| Docker build fails on Poetry deps   | Network proxy → add `--network host` or retry.     |
| Mac M‑series segfault (DuckDB)      | `brew install libomp` or run under Rosetta.        |

---

## 13 · Extension Ideas

* Swap synthetic data with real logs exporter.
* Parallelise platform agents via `asyncio.gather()`.
* Feed reviewer decisions back for RLHF fine‑tuning.
* Replace Streamlit with React + FastAPI, then containerise behind nginx.
* Add Grafana dashboard powering long‑term risk trends.

---

*End of Implementation Plan v1.1*
