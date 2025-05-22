# tests/test_pipeline.py
import subprocess
import pathlib
import json
import os
import pytest

# Define the root of the project where Makefile is located
PROJECT_ROOT = pathlib.Path(__file__).parent.parent 

# Ensure LLM_API_KEY is set for the test environment, or skip tests that require it.
# For local testing, it might be inherited from the shell. For CI, it needs to be set.
LLM_API_KEY_AVAILABLE = os.getenv("LLM_API_KEY") is not None

# Clean up previous run artifacts before testing
def clean_generated_files():
    files_to_remove = ["*.pss.json", "qsr_master.json", "data/qsr.duckdb", "data/*.parquet"]
    # Clean PSS files from root
    for pss_pattern in ["gemini.pss.json", "imagen.pss.json", "search.pss.json"]:
        pss_file = PROJECT_ROOT / pss_pattern
        if pss_file.exists():
            pss_file.unlink()
            print(f"Cleaned up: {pss_file}")
            
    # Clean qsr_master.json from root
    qsr_master_file = PROJECT_ROOT / "qsr_master.json"
    if qsr_master_file.exists():
        qsr_master_file.unlink()
        print(f"Cleaned up: {qsr_master_file}")

    # Clean files in data directory
    data_dir = PROJECT_ROOT / "data"
    if data_dir.exists():
        for pattern in ["qsr.duckdb", "*.parquet"]:
            for file_path in data_dir.glob(pattern):
                file_path.unlink()
                print(f"Cleaned up: {file_path}")
    else:
        data_dir.mkdir(exist_ok=True) # Ensure data dir exists if it was removed

@pytest.fixture(scope="module", autouse=True)
def setup_and_teardown():
    print("Running setup: Cleaning old files...")
    clean_generated_files()
    yield # This is where the tests will run
    print("Running teardown: Cleaning generated files after test...")
    # clean_generated_files() # Optionally clean up after tests too

@pytest.mark.skipif(not LLM_API_KEY_AVAILABLE, reason="LLM_API_KEY is not set. Skipping integration test.")
def test_make_demo_pipeline():
    """
    Tests the full 'make demo' pipeline.
    Checks if the command runs successfully and if the expected QSR JSON output is created.
    Also checks if the QSR contains a valid tier.
    """
    print(f"Running 'make demo' in {PROJECT_ROOT}...")
    
    # Run 'make demo' command
    # Using shell=True can be a security risk if command components are from untrusted input.
    # Here, 'make demo' is a fixed command.
    # Adding a timeout to prevent tests from hanging indefinitely.
    try:
        process = subprocess.run(
            "make demo", 
            shell=True, 
            cwd=PROJECT_ROOT, 
            capture_output=True, 
            text=True, 
            check=True,  # Raises CalledProcessError if return code is non-zero
            timeout=300  # 5 minutes timeout for the whole pipeline
        )
        print("STDOUT from 'make demo':")
        print(process.stdout)
        if process.stderr:
            print("STDERR from 'make demo':")
            print(process.stderr)
    except subprocess.CalledProcessError as e:
        print(f"Error running 'make demo': {e}")
        print("STDOUT:")
        print(e.stdout)
        print("STDERR:")
        print(e.stderr)
        pytest.fail(f"'make demo' command failed with exit code {e.returncode}")
    except subprocess.TimeoutExpired as e:
        print(f"Timeout running 'make demo': {e}")
        print("STDOUT:")
        print(e.stdout)
        print("STDERR:")
        print(e.stderr)
        pytest.fail("'make demo' command timed out.")


    # Check if the main output file (qsr_master.json) was created
    qsr_output_file = PROJECT_ROOT / "qsr_master.json"
    assert qsr_output_file.exists(), f"QSR output file not found at {qsr_output_file} after 'make demo'"

    # Check if the QSR JSON content is valid and contains expected fields
    with open(qsr_output_file, 'r') as f:
        try:
            qsr_data = json.load(f)
        except json.JSONDecodeError:
            pytest.fail(f"Could not decode JSON from QSR output file: {qsr_output_file}")

    assert "narrative" in qsr_data, "QSR JSON missing 'narrative' field"
    assert "risk_vector" in qsr_data, "QSR JSON missing 'risk_vector' field"
    assert "macro_patterns" in qsr_data, "QSR JSON missing 'macro_patterns' field"
    assert "recommended_action" in qsr_data, "QSR JSON missing 'recommended_action' field"
    
    # Check if recommended_action contains a 'tier'
    recommended_action = qsr_data.get("recommended_action", {})
    assert "tier" in recommended_action, "QSR recommended_action missing 'tier' field"
    
    # Check if the tier is a valid integer (0-3, or -1 for error cases as per aggregate_agent.py)
    tier = recommended_action.get("tier")
    assert isinstance(tier, int), f"QSR tier is not an integer: {tier}"
    assert -1 <= tier <= 3, f"QSR tier out of expected range (-1 to 3): {tier}"

    # Check if the DuckDB file was created (as aggregate_agent.py should persist to it)
    duckdb_file = PROJECT_ROOT / "data" / "qsr.duckdb"
    assert duckdb_file.exists(), f"DuckDB file not found at {duckdb_file} after 'make demo'"

    print(f"✓ Test 'test_make_demo_pipeline' passed. QSR Tier: {tier}")

# To run this test:
# 1. Ensure poetry environment is active: `poetry shell`
# 2. Ensure LLM_API_KEY is set: `export LLM_API_KEY="sk-..."` (or your actual key)
# 3. Run pytest from the project root: `pytest`
