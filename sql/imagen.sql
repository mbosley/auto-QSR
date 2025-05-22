INSTALL parquet; LOAD parquet;
CREATE OR REPLACE TABLE imagen_24h AS
SELECT *
FROM read_parquet('data/imagen.parquet')
WHERE ts BETWEEN now() - INTERVAL 1 DAY AND now();
