# -*- coding: utf-8 -*-

import os
import yaml
import shutil
import subprocess
import datetime
import time

BASE = os.path.expanduser("~")
DIRS = [
    os.path.join(BASE, "mvp-model-server"),
    os.path.join(BASE, "mvp-backend"),
    os.path.join(BASE, "mvp-frontend"),
]

def run(cmd, cwd=None):
    print("[RUN] {} (cwd={})".format(cmd, cwd))
    result = subprocess.run(cmd, shell=True, cwd=cwd)
    if result.returncode != 0:
        print("[ERROR] Command failed: {}".format(cmd))
        raise SystemExit(result.returncode)

def backup(path):
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = "{}.bak.{}".format(path, ts)
    shutil.copy(path, backup_path)
    print("[BACKUP] {}".format(backup_path))

def apply_restart_policy(path):
    print("\nProcessing: {}".format(path))
    backup(path)

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict) or "services" not in data:
        print("  [SKIP] No services block found.")
        return

    changed = False

    for name, svc in data["services"].items():
        if not isinstance(svc, dict):
            continue
        if "restart" not in svc:
            svc["restart"] = "unless-stopped"
            print("  + restart added for {}".format(name))
            changed = True
        else:
            print("  = restart exists for {}".format(name))

    if changed:
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, sort_keys=False)
        print("[UPDATED] {}".format(path))
    else:
        print("[NO CHANGE]")

def main():
    print("\n=== APPLYING RESTART POLICIES ===\n")

    for d in DIRS:
        path = os.path.join(d, "docker-compose.yml")
        if os.path.exists(path):
            apply_restart_policy(path)
        else:
            print("[WARN] Missing file: {}".format(path))

    print("\n=== STOPPING ALL SERVICES ===\n")
    run("docker compose down", cwd=os.path.join(BASE, "mvp-frontend"))
    run("docker compose down", cwd=os.path.join(BASE, "mvp-backend"))
    run("docker compose down", cwd=os.path.join(BASE, "mvp-model-server"))

    print("\n=== STARTING IN CORRECT ORDER ===\n")

    ms = os.path.join(BASE, "mvp-model-server")
    be = os.path.join(BASE, "mvp-backend")
    fe = os.path.join(BASE, "mvp-frontend")

    run("docker compose up -d --build server", cwd=ms)

    run("docker compose up -d db", cwd=be)
    print("Waiting 10 seconds for DB initialization...")
    time.sleep(10)

    run("docker compose up -d --build app", cwd=be)
    run("docker compose up -d --build job-queue-worker", cwd=be)
    run("docker compose up -d minio", cwd=be)

    run("docker compose up -d --build", cwd=fe)

    print("\n=== DONE ===")

if __name__ == "__main__":
    main()
