INSTALL parquet; LOAD parquet;
CREATE OR REPLACE TABLE search_24h AS
SELECT *
FROM read_parquet('data/search.parquet')
WHERE ts BETWEEN now() - INTERVAL 1 DAY AND now();
