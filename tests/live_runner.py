
import os
import subprocess
import sys

def run_live():
    # 1. Load key from .env manually
    key = None
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                if line.startswith("OPENAI_API_KEY="):
                    key = line.split("=")[1].strip()
                    break
    
    if not key:
        print("Error: OPENAI_API_KEY not found in .env")
        sys.exit(1)

    # 2. Prepare environment
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = key
    env["PYTHONPATH"] = env.get("PYTHONPATH", "") + ":" + os.getcwd()

    # 3. Run pytest
    print(f"Executing Live System Test with API key: {key[:8]}...")
    result = subprocess.run(
        ["pytest", "tests/test_live_system.py", "-s"],
        env=env,
        capture_output=False
    )
    sys.exit(result.returncode)

if __name__ == "__main__":
    run_live()
