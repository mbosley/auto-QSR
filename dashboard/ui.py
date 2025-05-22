import streamlit as st
import duckdb
import pandas as pd
import json
import pathlib

DB_PATH = pathlib.Path("data/qsr.duckdb") # Corrected path to be inside 'data' directory

def get_db_connection():
    # Connect, creating DB if it doesn't exist, in read-write mode initially if table needs creation
    # The table creation should ideally happen in the pipeline, not dashboard.
    # For robustness, dashboard connects read-only once data is expected.
    if not DB_PATH.exists():
        st.error(f"Database not found at {DB_PATH}. Run the 'make demo' pipeline first.")
        return None
    try:
        con = duckdb.connect(database=str(DB_PATH), read_only=True)
        return con
    except Exception as e:
        st.error(f"Error connecting to DuckDB: {e}")
        return None

def load_qsr_data(con):
    if con is None:
        return pd.DataFrame()
    try:
        # Check if the table exists
        tables = con.execute("SHOW TABLES").fetchall()
        if not any('qsr_reports' in t[0] for t in tables):
            st.error("Table 'qsr_reports' not found in the database. Run 'make demo' to generate data.")
            return pd.DataFrame()
            
        qsr_df = con.execute("SELECT * FROM qsr_reports ORDER BY report_ts DESC").df()
        return qsr_df
    except Exception as e:
        st.error(f"Error loading QSR data: {e}")
        return pd.DataFrame()

st.set_page_config(page_title="QSR Demo", layout="wide")
st.title("Qualitative Safety Report – Local Demo")

db_connection = get_db_connection()
qsr_data = load_qsr_data(db_connection)

if db_connection:
    db_connection.close()

if qsr_data.empty:
    st.warning("No QSR data found. Please run the `make demo` command in your terminal to generate reports.")
    st.stop()

# Display the latest QSR report
latest_qsr = qsr_data.iloc[0]

# Parse the JSON strings from the database
try:
    # The 'risk_vector' from DB is a JSON string, needs parsing for json_normalize
    # It might already be a dict if aggregate_agent.py directly inserts dicts (depends on DuckDB driver)
    # For safety, try to parse if it's a string.
    risk_vector_data = json.loads(latest_qsr["risk_vector"]) if isinstance(latest_qsr["risk_vector"], str) else latest_qsr["risk_vector"]
    risk_df = pd.json_normalize(risk_vector_data).T.rename(columns={0: "score"})
    
    # 'macro_patterns' from DB is a JSON string list
    macro_patterns_data = json.loads(latest_qsr["macro_patterns"]) if isinstance(latest_qsr["macro_patterns"], str) else latest_qsr["macro_patterns"]

    # 'raw_json' from DB is the full QSR JSON string
    raw_json_data = json.loads(latest_qsr["raw_json"]) if isinstance(latest_qsr["raw_json"], str) else latest_qsr["raw_json"]

except json.JSONDecodeError as e:
    st.error(f"Error parsing JSON data from the database: {e}")
    st.error(f"Problematic risk_vector: {latest_qsr['risk_vector']}")
    st.error(f"Problematic macro_patterns: {latest_qsr['macro_patterns']}")
    st.error(f"Problematic raw_json: {latest_qsr['raw_json']}")
    st.stop()
except Exception as e:
    st.error(f"An unexpected error occurred while processing QSR data: {e}")
    st.stop()


col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Narrative")
    st.write(latest_qsr["narrative"])

with col2:
    st.subheader("Risk Vector")
    if not risk_df.empty:
        st.bar_chart(risk_df)
    else:
        st.write("No risk vector data available.")

st.subheader("Macro-patterns")
if macro_patterns_data:
    for pattern in macro_patterns_data:
        st.markdown(f"- {pattern}")
else:
    st.write("No macro-patterns identified.")

st.subheader("Recommended Action (from QSR)")
if raw_json_data and "recommended_action" in raw_json_data:
    action = raw_json_data["recommended_action"]
    st.markdown(f"**Tier:** {action.get('tier', 'N/A')}")
    st.markdown(f"**Justification:** {action.get('justification', 'N/A')}")
else:
    st.write("No recommended action available.")


with st.expander("Raw QSR JSON"):
    st.json(raw_json_data)

with st.expander("Full QSR Table (Latest First)"):
    st.dataframe(qsr_data)
