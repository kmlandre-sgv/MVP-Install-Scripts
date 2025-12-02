import os
import sys
import subprocess
import shutil

# --- CONFIGURATION ---
STATE_FILE = "mvp_install_state.json"
BACKEND_DIR = "mvp-backend"
FRONTEND_DIR = "mvp-frontend"
MODEL_DIR = "mvp-model-server"

def print_header(msg):
    print(f"\n{'='*60}\n{msg}\n{'='*60}")

def run_cmd(cmd, cwd=None, ignore_error=True):
    print(f"[{cwd if cwd else 'root'}] Executing: {cmd}")
    try:
        subprocess.run(cmd, shell=True, cwd=cwd, check=True)
    except subprocess.CalledProcessError:
        if not ignore_error:
            print(f"Command failed: {cmd}")
            sys.exit(1)

def main():
    print_header("MVP Factory Reset (The Nuclear Option)")
    print("This will destroy ALL containers, volumes, and installation state.")
    
    confirm = input("Are you sure? This cannot be undone. (y/n): ").strip().lower()
    if confirm != 'y':
        print("Aborted.")
        sys.exit(0)

    base_path = os.getcwd()
    
    # 1. Stop and Remove Backend (WITH VOLUMES)
    print_header("Step 1: Destroying Backend & Database")
    backend_path = os.path.join(base_path, BACKEND_DIR)
    if os.path.exists(backend_path):
        # The '-v' flag is CRITICAL. It deletes the persistent database volume.
        run_cmd("docker compose down -v --remove-orphans", cwd=backend_path)
    else:
        print(f"Warning: {BACKEND_DIR} not found. Skipping.")

    # 2. Stop and Remove Frontend
    print_header("Step 2: Destroying Frontend")
    frontend_path = os.path.join(base_path, FRONTEND_DIR)
    if os.path.exists(frontend_path):
        run_cmd("docker compose down -v --remove-orphans", cwd=frontend_path)

    # 3. Stop and Remove Model Server
    print_header("Step 3: Destroying Model Server")
    model_path = os.path.join(base_path, MODEL_DIR)
    if os.path.exists(model_path):
        run_cmd("docker compose down -v --remove-orphans", cwd=model_path)

    # 4. Remove Network
    print_header("Step 4: Removing Network")
    run_cmd("docker network rm mvp-net")

    # 5. Remove Installation State
    print_header("Step 5: Removing Installation State")
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
        print(f"Deleted {STATE_FILE}")
    else:
        print("State file not found (clean).")

    # 6. Global Prune (Safety Net)
    print_header("Step 6: Final Sweep")
    print("Pruning any lingering volumes...")
    run_cmd("docker volume prune -f")

    print_header("Reset Complete")
    print("Your environment is now 100% clean.")
    print("You may now run: python install_mvp_resumable.py")

if __name__ == "__main__":
    main()