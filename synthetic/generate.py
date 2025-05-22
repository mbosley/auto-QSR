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
        "ts": now - dt.timedelta(minutes=rng.randint(0, 1440)),
        "text": rng.choice(intents[surface]),
        "policy_flag": rng.choice(["child_safety", "violence", "none", "extremism"])
    } for _ in range(n)]
    return pd.DataFrame(rows)

# Create the data directory if it doesn't exist
pathlib.Path("data").mkdir(exist_ok=True)

for s in ("gemini", "imagen", "search"):
    pq.write_table(pa.Table.from_pandas(sample(s)), f"data/{s}.parquet")
print("✓ Synthetic events saved → data/*.parquet")
