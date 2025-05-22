# src/platform_agent.py
import argparse
import json
import os
import pathlib
import sys
import duckdb
import datetime as dt

# Attempt to import LLM libraries
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None 

try:
    import google.generativeai as genai
except ImportError:
    genai = None 


DB_FILE = pathlib.Path("data/qsr.duckdb")
DEFAULT_LLM_MODEL = "gpt-4o-mini" # From Makefile

def get_llm_client_and_model():
    api_key = os.getenv("LLM_API_KEY")
    model_preference = os.getenv("LLM_MODEL", DEFAULT_LLM_MODEL)

    if not api_key:
        raise ValueError("LLM_API_KEY environment variable not set.")

    # Prioritize explicit model prefixes
    if model_preference.startswith("gpt") and OpenAI:
        client = OpenAI(api_key=api_key)
        return client, model_preference, "openai"
    elif model_preference.startswith("gemini") and genai:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_preference)
        return model, model_preference, "google"
    
    # Fallback if no clear prefix but a library is available
    elif OpenAI: 
        print(f"Warning: Model '{model_preference}' prefix unclear, defaulting to OpenAI compatible.")
        client = OpenAI(api_key=api_key)
        return client, model_preference, "openai" # Assume it's an OpenAI model name
    elif genai: 
        print(f"Warning: Model '{model_preference}' prefix unclear, defaulting to Google Gemini compatible.")
        genai.configure(api_key=api_key)
        # Use a known compatible Gemini model if preference is not clearly a gemini model name
        gemini_model_name = model_preference if model_preference.startswith("gemini") else "gemini-pro" 
        model = genai.GenerativeModel(gemini_model_name)
        return model, gemini_model_name, "google"
    else:
        raise ValueError("Neither OpenAI nor Google Generative AI libraries are installed, or LLM_MODEL is incompatible.")


def query_llm(client_or_model, model_name, llm_provider, system_prompt, user_content):
    if llm_provider == "openai":
        chat_completion = client_or_model.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            model=model_name,
            response_format={"type": "json_object"}, 
        )
        return chat_completion.choices[0].message.content
    elif llm_provider == "google":
        full_prompt_for_gemini = system_prompt + "\n\n" + user_content # Combine system and user for Gemini
        
        response = client_or_model.generate_content(full_prompt_for_gemini)
        
        json_text = ""
        # Try to extract text from response, accommodating different possible structures
        if hasattr(response, 'text') and response.text:
            json_text = response.text
        elif hasattr(response, 'parts') and response.parts:
            for part in response.parts:
                if hasattr(part, 'text') and part.text:
                    json_text += part.text
        
        if not json_text:
            # If text is still empty, check if the error is due to safety settings / finish_reason
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
                 raise ValueError(f"Gemini content generation stopped due to: {response.prompt_feedback.block_reason_message or response.prompt_feedback.block_reason}")
            raise ValueError("Could not extract text from Gemini response. Response may be empty or malformed.")

        # Clean up potential markdown formatting around JSON
        if json_text.strip().startswith("```json"):
            json_text = json_text.strip()[7:-3].strip()
        elif json_text.strip().startswith("```"):
             json_text = json_text.strip()[3:-3].strip()
        return json_text
    return None

def main():
    parser = argparse.ArgumentParser(description="Platform Safety Agent")
    parser.add_argument("--surface", required=True, help="Name of the platform (e.g., gemini, imagen, search)")
    parser.add_argument("--out", required=True, help="Output file path for the JSON summary (e.g., gemini.pss.json)")
    args = parser.parse_args()

    print(f"Starting Platform Safety Agent for surface: {args.surface}")

    prompt_file = pathlib.Path(f"prompts/platform_prompt.txt")
    if not prompt_file.exists():
        print(f"Error: Prompt file not found at {prompt_file}"); sys.exit(1)
    with open(prompt_file, 'r') as f: platform_prompt_template = f.read()
    
    system_prompt_content = platform_prompt_template.split("TASK")[0].replace("{surface}", args.surface.capitalize()).strip()
    user_task_instruction = "TASK" + platform_prompt_template.split("TASK")[1].strip()

    if not DB_FILE.exists():
        print(f"Error: DB {DB_FILE} not found. Run 'make extract' first."); sys.exit(1)

    try:
        con = duckdb.connect(database=str(DB_FILE), read_only=True)
        table_name = f"{args.surface}_24h"
        tables_in_db = con.execute("SHOW TABLES").fetchall()
        if not any(table_name.lower() in t[0].lower() for t in tables_in_db): # Case-insensitive check
            print(f"Error: Table '{table_name}' not found in {DB_FILE}. Ran 'make sql_{args.surface}'?"); con.close(); sys.exit(1)
        
        data_df = con.execute(f"SELECT * FROM {table_name};").df()
        con.close()
    except Exception as e:
        print(f"Error connecting/querying DuckDB: {e}"); sys.exit(1)

    if data_df.empty:
        print(f"Warning: No data found for surface {args.surface}. Generating an empty summary.")
        summary_data = {"incidents": [], "summary": f"No activity recorded for {args.surface} in the last 24 hours."}
    else:
        events_json_str = data_df.to_json(orient="records", date_format="iso")
        user_content_for_llm = f"Analyze the following user activity events for surface '{args.surface}'. The events are provided as a JSON array:\n{events_json_str}\n\n{user_task_instruction}"

        try:
            client, model_name, llm_provider = get_llm_client_and_model()
            print(f"Using {llm_provider} model: {model_name} for {args.surface}")
            
            raw_llm_response_str = query_llm(client, model_name, llm_provider, system_prompt_content, user_content_for_llm)
            summary_data = json.loads(raw_llm_response_str) 

        except Exception as e:
            print(f"Error during LLM query or parsing response for {args.surface}: {e}")
            summary_data = {"incidents": [], "summary": f"Error processing data for {args.surface}: {str(e)}", "error": True}

    output_path = pathlib.Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f: json.dump(summary_data, f, indent=2)
    
    print(f"✓ Platform summary for {args.surface} saved to {args.out}")

if __name__ == "__main__":
    main()
