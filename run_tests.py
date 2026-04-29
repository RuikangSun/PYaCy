import subprocess, sys
result = subprocess.run(
    [r"C:/Users/srk88/miniconda3/envs/crawler/python.exe", "-m", "pytest", "tests/", "-v", "--tb=short"],
    cwd=r"C:\Users\srk88\.openakita\workspaces\default\data\PYaCy",
    capture_output=True, text=True, timeout=180,
    env={**__import__("os").environ, "PYTHONPATH": r"C:\Users\srk88\.openakita\workspaces\default\data\PYaCy\src"}
)
lines = result.stdout.splitlines()
# Print summary: last 100 lines
for line in lines[-100:]:
    print(line)
if result.stderr:
    print("=== STDERR ===")
    for line in result.stderr.splitlines()[-20:]:
        print(line)
sys.exit(0)
