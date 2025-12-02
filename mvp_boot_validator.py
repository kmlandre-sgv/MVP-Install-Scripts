# -*- coding: utf-8 -*-

import subprocess
import socket
import requests
import time


EXPECTED_CONTAINERS = [
    "mvp-frontend-app-1",
    "api-server",
    "mvp-backend-job-queue-worker-1",
    "mvp-backend-db-1",
    "minio",
    "machine-learning-server"
]

PORTS = {
    8000: "Frontend",
    8001: "Backend API",
    8003: "MinIO API",
    8004: "MinIO Console"
}


def run(cmd):
    """Run a shell command and return (success, stdout)."""
    try:
        out = subprocess.check_output(cmd, shell=True, text=True)
        return True, out
    except subprocess.CalledProcessError as e:
        return False, e.output


def check_port(port):
    """Check if a TCP port is listening."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    result = sock.connect_ex(("127.0.0.1", port))
    sock.close()
    return result == 0


def get_public_ip():
    """Retrieve EC2 public IP using IMDSv2 with automatic fallback."""
    try:
        # Step 1: Get IMDSv2 token
        token = requests.put(
            "http://169.254.169.254/latest/api/token",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
            timeout=1,
        ).text

        if token:
            # Step 2: Request public IP using token
            ip = requests.get(
                "http://169.254.169.254/latest/meta-data/public-ipv4",
                headers={"X-aws-ec2-metadata-token": token},
                timeout=1,
            ).text.strip()
            return ip if ip else None
    except Exception:
        pass

    # Final fallback (will still likely fail on hardened instances)
    try:
        r = requests.get("http://169.254.169.254/latest/meta-data/public-ipv4", timeout=1)
        return r.text.strip()
    except Exception:
        return None



def check_http(url):
    """Return HTTP status code or None."""
    try:
        r = requests.get(url, timeout=2)
        return r.status_code
    except Exception:
        return None


def main():
    print("\n============================================================")
    print("MVP System Post-Reboot Health Check")
    print("============================================================\n")

    # 1. Docker service
    print("[1] Checking Docker status...")
    success, out = run("systemctl is-active docker")
    if not success or "active" not in out:
        print("  ERROR: Docker is not running.")
        return
    print("  Docker is running.\n")

    # 2. Container inventory
    print("[2] Checking expected containers...\n")
    success, all_containers = run("docker ps -a --format '{{.Names}}'")
    running_containers = all_containers.splitlines()

    for c in EXPECTED_CONTAINERS:
        if c in running_containers:
            print("  FOUND: " + c)
        else:
            print("  MISSING: " + c)

    print("\n[3] Checking container running state...\n")
    success, running_list = run("docker ps --format '{{.Names}}'")
    running_list = running_list.splitlines()

    for c in EXPECTED_CONTAINERS:
        if c in running_list:
            print("  OK: " + c + " is running.")
        else:
            print("  ERROR: " + c + " is not running.")

    # 4. DB health
    print("\n[4] Checking Postgres health...\n")
    success, db_status = run("docker ps --filter 'name=mvp-backend-db-1' --format '{{.Status}}'")
    db_status = db_status.strip()
    print("  DB status: " + db_status)

    if "healthy" in db_status.lower():
        print("  OK: Database is healthy.")
    else:
        print("  WARNING: Database is not healthy yet.")

    # 5. Port checks
    print("\n[5] Checking port bindings...\n")
    for port, desc in PORTS.items():
        if check_port(port):
            print("  OK: " + desc + " on port " + str(port) + " is listening")
        else:
            print("  ERROR: " + desc + " on port " + str(port) + " is not listening")

    # 6. Public + Local HTTP checks
    print("\n[6] Checking HTTP endpoints...\n")
    public_ip = get_public_ip()

    # Always check localhost
    localhost_ip = "127.0.0.1"

    def check_both(name, port, path=""):
        local_url = f"http://{localhost_ip}:{port}{path}"
        external_url = None if not public_ip else f"http://{public_ip}:{port}{path}"

        local_status = check_http(local_url)
        print(f"  {name} (local {local_url}) -> {local_status}")

        if external_url:
            ext_status = check_http(external_url)
            print(f"  {name} (public {external_url}) -> {ext_status}")
        else:
            print("  WARNING: No public IP available; skipping external check.")

    # Frontend
    check_both("Frontend", 8000)

    # Backend
    check_both("Backend", 8001, "/health")

    # MinIO API
    check_both("MinIO", 8003)

    print("\n============================================================")
    print("HEALTH CHECK COMPLETE")
    print("============================================================\n")


if __name__ == "__main__":
    main()
