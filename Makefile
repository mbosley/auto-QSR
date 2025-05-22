LLM_MODEL ?= gpt-4o-mini
SURFACES  := gemini imagen search

.PHONY: generate extract pss qsr demo clean sql_gemini sql_imagen sql_search

generate:
	python synthetic/generate.py

sql_gemini: sql/gemini.sql
	python src/run_sql_duckdb.py sql/gemini.sql

sql_imagen: sql/imagen.sql
	python src/run_sql_duckdb.py sql/imagen.sql

sql_search: sql/search.sql
	python src/run_sql_duckdb.py sql/search.sql

extract: sql_gemini sql_imagen sql_search

gemini.pss.json: extract
	python src/platform_agent.py --surface gemini --out gemini.pss.json

imagen.pss.json: extract
	python src/platform_agent.py --surface imagen --out imagen.pss.json

search.pss.json: extract
	python src/platform_agent.py --surface search --out search.pss.json

pss: gemini.pss.json imagen.pss.json search.pss.json

qsr: pss
	python src/aggregate_agent.py prompts/aggregate_prompt.txt qsr_master.json

demo: generate extract pss qsr
	@echo "✓ Pipeline done →  streamlit run dashboard/ui.py"

clean:
	rm -f *.pss.json qsr_master.json data/qsr.duckdb data/*.parquet
