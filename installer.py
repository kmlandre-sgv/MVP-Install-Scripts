import os
import sys
import subprocess
import re
import time
import shutil
import json
import datetime

STATE_FILE = "mvp_install_state.json"
LOG_FILE = f"installer_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
REQUIRED_DIRS = ["mvp-model-server", "mvp-backend", "mvp-frontend"]

DEFAULT_MINIO_PASS = "MinioSecurePass2025"
STRICT_DB_PASS = "surgivance" 

class Logger:
    def __init__(self, filename):
        self.filename = filename
        with open(self.filename, 'w') as f:
            f.write(f"MVP Final Fix Installer - Started at {datetime.datetime.now()}\n")
            f.write("="*60 + "\n\n")

    def log(self, message, header=False):
        timestamp = datetime.datetime.now().strftime("[%H:%M:%S]")
        if header:
            print(f"\n{'='*60}\n{message}\n{'='*60}")
            with open(self.filename, 'a') as f:
                f.write(f"\n{'='*60}\n{message}\n{'='*60}\n")
        else:
            print(message)
            with open(self.filename, 'a') as f:
                f.write(f"{timestamp} {message}\n")

    def log_cmd_output(self, output):
        if not output: return
        with open(self.filename, 'a') as f:
            f.write("  [CMD OUTPUT START]\n")
            f.write(output)
            f.write("  [CMD OUTPUT END]\n")

logger = Logger(LOG_FILE)

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.log("Warning: State file corrupted. Starting fresh.")
    return {}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)
    logger.log(f"   [State Saved] to {STATE_FILE}")

def get_input(prompt, key, state, default_val=None):
    if key in state and state[key]:
        logger.log(f"{prompt}: [Using cached value: {state[key]}]")
        return state[key]
    
    val = ""
    if default_val:
        user_in = input(f"{prompt} [Default: {default_val}]: ").strip()
        val = user_in if user_in else default_val
    else:
        while True:
            user_in = input(f"{prompt}: ").strip()
            if user_in:
                val = user_in
                break
    
    if "password" in prompt.lower() or "key" in prompt.lower():
        logger.log(f"User Input for {key}: [REDACTED]")
    else:
        logger.log(f"User Input for {key}: {val}")

    state[key] = val
    save_state(state) 
    return val

def run_cmd(cmd, cwd=None, exit_on_fail=True, capture_output=False):
    logger.log(f"[{cwd if cwd else 'root'}] Executing: {cmd}")
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            cwd=cwd, 
            check=True, 
            text=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        )
        logger.log_cmd_output(result.stdout)
        if capture_output:
            return result.stdout
        else:
            logger.log("  [Command Success]")
            return True
    except subprocess.CalledProcessError as e:
        logger.log(f"Error executing command: {cmd}")
        logger.log(f"STDERR: {e.stderr}")
        logger.log_cmd_output(e.stdout)
        if exit_on_fail:
            sys.exit(1)
        return False

def sed_replace(file_path, pattern, replacement):
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        if not re.search(pattern, content, re.MULTILINE):
            logger.log(f"Warning: Pattern '{pattern}' not found in {file_path}")
            return

        new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
        
        with open(file_path, 'w') as f:
            f.write(new_content)
        logger.log(f"Updated configuration in {file_path}")
    except Exception as e:
        logger.log(f"Failed to edit file {file_path}: {e}")
        sys.exit(1)

def main():
    logger.log("MVP Final Fix Installer", header=True)
    
    state = load_state()
    if state:
        resume = input("Resume from last successful step? (y/n) [y]: ").strip().lower()
        if resume == 'n':
            logger.log("Wiping state and starting fresh...")
            state = {}
            if os.path.exists(STATE_FILE): os.remove(STATE_FILE)
        else:
            logger.log("Resuming...")
    
    if not shutil.which("docker"):
        logger.log("Error: Docker is not installed.")
        sys.exit(1)

    if not state.get("step_1_workspace_done"):
        logger.log("Step 1: Verifying Workspace", header=True)
        base_input = get_input("Enter path containing 'mvp-' directories", "base_path", state, ".")
        abs_base_path = os.path.abspath(base_input)
        missing = [d for d in REQUIRED_DIRS if not os.path.isdir(os.path.join(abs_base_path, d))]
        if missing:
            logger.log(f"Error: Missing directories: {missing}")
            sys.exit(1)
        state["abs_base_path"] = abs_base_path
        state["step_1_workspace_done"] = True
        save_state(state)
    
    abs_base_path = state["abs_base_path"]

    if not state.get("step_2_network_done"):
        logger.log("Step 2: Network Setup", header=True)
        net_check = run_cmd("docker network ls", capture_output=True)
        if "mvp-net" not in net_check:
            run_cmd("docker network create mvp-net")
        state["step_2_network_done"] = True
        save_state(state)

    if not state.get("step_3_model_done"):
        logger.log("Step 3: Model Server", header=True)
        model_dir = os.path.join(abs_base_path, "mvp-model-server")
        is_local = get_input("Is this a Local Deployment? (y/n)", "is_local", state, "n").lower() == 'y'
        
        if is_local:
            sed_replace(os.path.join(model_dir, "docker-compose.yml"), r'^\s*runtime:\s*nvidia.*$', r'# runtime: nvidia')
        
        run_cmd("docker compose up -d --build server", cwd=model_dir)
        state["step_3_model_done"] = True
        save_state(state)

    if not state.get("step_4_minio_start_done"):
        logger.log("Step 4: MinIO Setup", header=True)
        backend_dir = os.path.join(abs_base_path, "mvp-backend")
        minio_pwd = get_input("MinIO Password", "minio_pwd", state, DEFAULT_MINIO_PASS)
        
        sed_replace(
            os.path.join(backend_dir, "docker-compose.yml"),
            r'^\s*MINIO_ROOT_PASSWORD:.*$',
            f'      MINIO_ROOT_PASSWORD: {minio_pwd}'
        )
        run_cmd("docker compose up -d minio", cwd=backend_dir)
        logger.log("Waiting for MinIO...")
        time.sleep(10)
        state["step_4_minio_start_done"] = True
        save_state(state)

    if not state.get("step_5_keys_done"):
        logger.log("Step 5: MinIO Keys", header=True)
        backend_dir = os.path.join(abs_base_path, "mvp-backend")
        minio_pwd = state["minio_pwd"]
        
        run_cmd(f"docker compose exec minio mc alias set myminio http://localhost:9000 surgivance {minio_pwd}", cwd=backend_dir)
        key_out = run_cmd("docker compose exec minio mc admin accesskey create myminio surgivance", cwd=backend_dir, capture_output=True)
        
        ak_match = re.search(r'Access Key:\s*([^\s\r\n]+)', key_out)
        sk_match = re.search(r'Secret Key:\s*([^\s\r\n]+)', key_out)
        
        if not ak_match or not sk_match:
            logger.log("Error parsing MinIO keys.")
            sys.exit(1)
            
        state["access_key"] = ak_match.group(1)
        state["secret_key"] = sk_match.group(1)
        state["step_5_keys_done"] = True
        save_state(state)

    if not state.get("step_6_backend_done"):
        logger.log("Step 6: Backend Config", header=True)
        backend_dir = os.path.join(abs_base_path, "mvp-backend")
        compose_file = os.path.join(backend_dir, "docker-compose.yml")
        
        postgres_pwd = STRICT_DB_PASS
        logger.log(f"ENFORCING Database Password: {postgres_pwd}")
        
        sed_replace(
            compose_file,
            r'^\s*REMOTE_STORAGE_ACCESS_KEY:.*$',
            f'      REMOTE_STORAGE_ACCESS_KEY: {state["access_key"]}'
        )

        sed_replace(
            compose_file,
            r'^\s*REMOTE_STORAGE_SECRET_KEY:.*$',
            f'      REMOTE_STORAGE_SECRET_KEY: {state["secret_key"]}'
        )

        sed_replace(
            compose_file,
            r'^\s*POSTGRES_PASSWORD:.*$', 
            f'      POSTGRES_PASSWORD: {postgres_pwd}'
        )

        sed_replace(
            compose_file,
            r'^\s*DATABASE_URL:.*$',
            f'      DATABASE_URL: postgresql://postgres:{postgres_pwd}@db:5432/postgres'
        )
        
        run_cmd("docker compose up -d --build app", cwd=backend_dir)
        state["step_6_backend_done"] = True
        save_state(state)

    if not state.get("step_7_db_init_done"):
        logger.log("Step 7: Database Init & Self-Healing", header=True)
        backend_dir = os.path.join(abs_base_path, "mvp-backend")
        
        run_cmd("docker compose up -d db", cwd=backend_dir)
        logger.log("Waiting 10s for DB...")
        time.sleep(10)
        
        logger.log("Attempting DB Reset...")
        success = run_cmd("docker compose exec app python -m src.models.db_reset", cwd=backend_dir, exit_on_fail=False)
        
        if not success:
            logger.log("!!! DETECTED AUTH FAILURE !!!", header=True)
            logger.log("Initiating SELF-HEALING to fix 'Zombie Volume'...")
            
            run_cmd("docker compose stop db", cwd=backend_dir)
            run_cmd("docker compose rm -f db", cwd=backend_dir)
            
            vol_name = "mvp-backend_postgres_data"
            logger.log(f"Deleting corrupt volume: {vol_name}")
            run_cmd(f"docker volume rm {vol_name}", exit_on_fail=False)
            
            logger.log("Rebuilding Database with correct password...")
            run_cmd("docker compose up -d db", cwd=backend_dir)
            logger.log("Waiting 15s for fresh initialization...")
            time.sleep(15)
            
            run_cmd("docker compose restart app", cwd=backend_dir)
            time.sleep(5)
            
            logger.log("Retrying DB Reset...")
            retry = run_cmd("docker compose exec app python -m src.models.db_reset", cwd=backend_dir)
            if retry:
                logger.log("SELF-HEALING SUCCESSFUL!")
            else:
                logger.log("Critical Failure: Unable to fix DB.")
                sys.exit(1)
                
        state["step_7_db_init_done"] = True
        save_state(state)

    if not state.get("step_8_worker_done"):
        logger.log("Step 8: Worker", header=True)
        run_cmd("docker compose up -d --build job-queue-worker", cwd=os.path.join(abs_base_path, "mvp-backend"))
        state["step_8_worker_done"] = True
        save_state(state)

    if not state.get("step_9_frontend_done"):
        logger.log("Step 9: Frontend", header=True)
        f_dir = os.path.join(abs_base_path, "mvp-frontend")
        
        if get_input("Setup Basic Auth? (y/n)", "setup_auth", state, "n").lower() == 'y':
            user = get_input("Username", "ba_user", state, "admin")
            pw = get_input("Password", "ba_pass", state, "secure")
            
            sed_replace(
                os.path.join(f_dir, "docker-compose.yml"),
                r'^\s*#\s*BASIC_AUTH_USERNAME:.*$',
                f'# BASIC_AUTH_USERNAME: {user}'
            )

            sed_replace(
                os.path.join(f_dir, "docker-compose.yml"),
                r'^\s*#\s*BASIC_AUTH_PASSWORD:.*$',
                f'# BASIC_AUTH_PASSWORD: {pw}'
            )
            
        run_cmd("docker compose up -d --build", cwd=f_dir)
        state["step_9_frontend_done"] = True
        save_state(state)

    logger.log("INSTALLATION COMPLETE", header=True)
    logger.log("Access: http://localhost:8000/")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
