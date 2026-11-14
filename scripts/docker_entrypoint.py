import argparse
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="VendOps Container Entrypoint")
    parser.add_argument(
        "--mode",
        choices=["api", "demo", "eval", "mcp"],
        default="api",
        help="Execution mode (default: api)",
    )
    args, unknown = parser.parse_known_args()

    if args.mode == "api":
        cmd = ["uvicorn", "vendops.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
    elif args.mode == "mcp":
        cmd = ["python", "-m", "vendops.mcp_server.server", "--http", "--port", "8001"]
    elif args.mode == "demo":
        cmd = ["python", "scripts/demo.py"]
    elif args.mode == "eval":
        cmd = ["python", "evals/run_eval.py"]
    else:
        cmd = ["uvicorn", "vendops.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

    sys.exit(subprocess.call(cmd + unknown))


if __name__ == "__main__":
    main()
