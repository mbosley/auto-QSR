INSTALL parquet; LOAD parquet;
CREATE OR REPLACE TABLE gemini_24h AS
SELECT *
FROM read_parquet('data/gemini.parquet')
WHERE ts BETWEEN now() - INTERVAL 1 DAY AND now();
