# src/aggregate_agent.py
import argparse
import json
import os
import pathlib
import sys
import duckdb
import datetime as dt

# Re-use LLM logic (ideally from a shared utils.py)
try:
    from openai import OpenAI
except ImportError: OpenAI = None
try:
    import google.generativeai as genai
except ImportError: genai = None

DB_FILE = pathlib.Path("data/qsr.duckdb")
DEFAULT_LLM_MODEL = "gpt-4o-mini" # From Makefile
PLATFORM_SURFACES = ["gemini", "imagen", "search"] # From Makefile

def get_llm_client_and_model(): # Identical to platform_agent's
    api_key = os.getenv("LLM_API_KEY")
    model_preference = os.getenv("LLM_MODEL", DEFAULT_LLM_MODEL)
    if not api_key: raise ValueError("LLM_API_KEY not set.")
    if model_preference.startswith("gpt") and OpenAI:
        return OpenAI(api_key=api_key), model_preference, "openai"
    if model_preference.startswith("gemini") and genai:
        genai.configure(api_key=api_key)
        return genai.GenerativeModel(model_preference), model_preference, "google"
    if OpenAI: 
        return OpenAI(api_key=api_key), model_preference, "openai"
    if genai:
        genai.configure(api_key=api_key)
        gmodel = model_preference if model_preference.startswith("gemini") else "gemini-pro"
        return genai.GenerativeModel(gmodel), gmodel, "google"
    raise ValueError("LLM client setup failed.")

def query_llm(client_or_model, model_name, llm_provider, system_prompt, user_content): # Identical to platform_agent's
    if llm_provider == "openai":
        comp = client_or_model.chat.completions.create(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
            model=model_name, response_format={"type": "json_object"})
        return comp.choices[0].message.content
    if llm_provider == "google":
        full_prompt = system_prompt + "\n\n" + user_content
        resp = client_or_model.generate_content(full_prompt)
        json_text = ""
        if hasattr(resp, 'text') and resp.text: json_text = resp.text
        elif hasattr(resp, 'parts') and resp.parts:
            json_text = "".join(p.text for p in resp.parts if hasattr(p, 'text'))
        if not json_text:
            if hasattr(resp, 'prompt_feedback') and resp.prompt_feedback.block_reason:
                 raise ValueError(f"Gemini content generation stopped due to: {resp.prompt_feedback.block_reason_message or resp.prompt_feedback.block_reason}")
            raise ValueError("No text from Gemini response")
        if json_text.strip().startswith("```json"): json_text = json_text.strip()[7:-3].strip()
        elif json_text.strip().startswith("```"): json_text = json_text.strip()[3:-3].strip()
        return json_text
    return None

def main():
    parser = argparse.ArgumentParser(description="Aggregate Safety Report Agent")
    parser.add_argument("aggregate_prompt_file", help="Path to the aggregate prompt file (e.g., prompts/aggregate_prompt.txt)")
    parser.add_argument("output_qsr_file", help="Path to save the final QSR JSON (e.g., qsr_master.json)")
    args = parser.parse_args()

    print("Starting Aggregate Safety Report Agent.")

    agg_prompt_path = pathlib.Path(args.aggregate_prompt_file)
    if not agg_prompt_path.exists(): 
        print(f"Error: Aggregate prompt file not found at {agg_prompt_path}"); sys.exit(1)
    with open(agg_prompt_path, 'r') as f: aggregate_prompt_template = f.read()
    
    system_prompt_content = aggregate_prompt_template.split("TASK")[0].strip()
    user_task_instruction = "TASK" + aggregate_prompt_template.split("TASK")[1].strip()

    platform_data_for_llm = {}
    found_any_pss = False
    for surface in PLATFORM_SURFACES:
        pss_file = pathlib.Path(f"{surface}.pss.json") # As per Makefile, these are in root project directory
        if pss_file.exists():
            try:
                with open(pss_file, 'r') as f: 
                    data = json.load(f)
                    # Basic validation: check if it has 'incidents' and 'summary' keys as expected by prompts
                    if isinstance(data, dict) and "incidents" in data and "summary" in data:
                        platform_data_for_llm[surface] = data
                        print(f"Successfully loaded and validated PSS for {surface} from {pss_file}")
                        found_any_pss = True
                    else:
                        print(f"Warning: PSS file {pss_file} for {surface} has invalid structure. Skipping.")
                        platform_data_for_llm[surface] = {"error": f"Invalid structure in {pss_file}", "incidents": [], "summary": ""}
            except json.JSONDecodeError:
                print(f"Warning: Could not decode JSON from {pss_file} for {surface}. Skipping.")
                platform_data_for_llm[surface] = {"error": f"Invalid JSON in {pss_file}", "incidents": [], "summary": ""}
            except Exception as e:
                 print(f"Warning: Error loading PSS {pss_file}: {e}. Skipping.")
                 platform_data_for_llm[surface] = {"error": str(e), "incidents": [], "summary": ""}
        else:
            print(f"Warning: PSS file {pss_file} for {surface} not found. It will be included as 'data not available'.")
            platform_data_for_llm[surface] = {"error": f"File not found: {pss_file}", "incidents": [], "summary": "Data not available"}

    if not found_any_pss : # If no PSS files had actual valid data (e.g. all were missing or malformed)
        print("Error: No valid Platform Safety Summaries loaded. Cannot generate QSR.")
        qsr_data = { 
            "narrative": "Failed to generate QSR: No valid platform summaries were found or loaded.",
            "risk_vector": {}, "macro_patterns": [],
            "recommended_action": {"tier": -1, "justification": "No platform data."}, "error": True
        }
    else:
        combined_pss_json_str = json.dumps(platform_data_for_llm) 
        user_content_for_llm = f"Aggregate the following platform safety summaries (provided as a JSON object where keys are platform names):\n{combined_pss_json_str}\n\n{user_task_instruction}"
        
        try:
            client, model_name, llm_provider = get_llm_client_and_model()
            print(f"Using {llm_provider} model: {model_name} for QSR generation.")
            
            raw_qsr_str = query_llm(client, model_name, llm_provider, system_prompt_content, user_content_for_llm)
            qsr_data = json.loads(raw_qsr_str)
        except Exception as e:
            print(f"Error during QSR LLM query or parsing: {e}")
            qsr_data = {"narrative": f"Error generating QSR: {str(e)}", "risk_vector": {}, "macro_patterns": [], "recommended_action": {"tier": -1, "justification": "Error in QSR generation."}, "error": True}

    output_qsr_path = pathlib.Path(args.output_qsr_file)
    output_qsr_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_qsr_path, 'w') as f: json.dump(qsr_data, f, indent=2)
    print(f"✓ QSR JSON saved to {args.output_qsr_file}")

    DB_FILE.parent.mkdir(parents=True, exist_ok=True) 
    try:
        con = duckdb.connect(database=str(DB_FILE), read_only=False)
        con.execute("""
            CREATE TABLE IF NOT EXISTS qsr_reports (
                report_ts TIMESTAMP DEFAULT now(), narrative VARCHAR, risk_vector VARCHAR,
                macro_patterns VARCHAR, recommended_action VARCHAR, raw_json VARCHAR)""")
        
        narrative_val = qsr_data.get("narrative", "N/A due to error" if qsr_data.get("error") else "")
        risk_vector_val = qsr_data.get("risk_vector", {})
        macro_patterns_val = qsr_data.get("macro_patterns", [])
        recommended_action_val = qsr_data.get("recommended_action", {"tier": -1, "justification": "N/A due to error"} if qsr_data.get("error") else {})

        con.execute("INSERT INTO qsr_reports (narrative, risk_vector, macro_patterns, recommended_action, raw_json) VALUES (?, ?, ?, ?, ?)",
                    [narrative_val, json.dumps(risk_vector_val), 
                     json.dumps(macro_patterns_val), json.dumps(recommended_action_val),
                     json.dumps(qsr_data)])
        con.close()
        print(f"✓ QSR data persisted to DuckDB table 'qsr_reports' in {DB_FILE}")
    except Exception as e:
        print(f"Error persisting QSR to DuckDB: {e}")

if __name__ == "__main__":
    main()
