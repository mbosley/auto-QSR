# src/run_sql_duckdb.py
import sys
import duckdb
import pathlib

DB_FILE = pathlib.Path("data/qsr.duckdb")

def main():
    if len(sys.argv) < 2:
        print("Usage: python src/run_sql_duckdb.py <path_to_sql_file>")
        print("Example: python src/run_sql_duckdb.py sql/gemini.sql")
        sys.exit(1)

    sql_file_path = pathlib.Path(sys.argv[1])

    if not sql_file_path.exists():
        print(f"Error: SQL file not found at {sql_file_path}")
        sys.exit(1)

    print(f"Attempting to run SQL script: {sql_file_path} on DB: {DB_FILE}")

    DB_FILE.parent.mkdir(parents=True, exist_ok=True)

    try:
        con = duckdb.connect(database=str(DB_FILE), read_only=False)
        with open(sql_file_path, 'r') as f:
            sql_script = f.read()
        
        con.execute(sql_script) # DuckDB can execute multiple statements separated by semicolons
        con.close()
        print(f"✓ Successfully executed SQL script: {sql_file_path}")
    except Exception as e:
        print(f"Error executing SQL script {sql_file_path}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
