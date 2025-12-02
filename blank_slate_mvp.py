import subprocess
import sys
import json

# Configuration
TARGET_NETWORK = "mvp-net"

def print_header(msg):
    print(f"\n{'='*60}\n{msg}\n{'='*60}")

def run_cmd(cmd, exit_on_fail=False, capture_output=True):
    """Runs a shell command and returns output."""
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            check=True, 
            text=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        if exit_on_fail:
            print(f"Critical Error executing: {cmd}")
            print(e.stderr)
            sys.exit(1)
        return None

def get_containers_in_network(network_name):
    """
    Finds all containers (running or stopped) attached to the specific network.
    Returns a list of dicts containing ID and Image ID.
    """
    # Check if network exists first
    check = run_cmd(f"docker network inspect {network_name}")
    if not check:
        return []

    # Get container IDs associated with the network
    # We use docker ps -a with filter to catch stopped containers too
    cmd = f'docker ps -a --filter "network={network_name}" --format "{{{{.ID}}}}|{{{{.Image}}}}|{{{{.Names}}}}"'
    output = run_cmd(cmd)
    
    containers = []
    if output:
        for line in output.split('\n'):
            parts = line.split('|')
            if len(parts) == 3:
                containers.append({
                    "id": parts[0],
                    "image": parts[1],
                    "name": parts[2]
                })
    return containers

def cleanup_process():
    print_header(f"MVP Environment Cleanup: {TARGET_NETWORK}")
    
    # 1. Identify Network and Containers
    print(f"Scanning network '{TARGET_NETWORK}' for artifacts...")
    containers = get_containers_in_network(TARGET_NETWORK)
    
    if not containers:
        # Check if network exists even if empty
        net_exists = run_cmd(f"docker network inspect {TARGET_NETWORK}")
        if not net_exists:
            print(f"Network '{TARGET_NETWORK}' not found. Environment appears clean.")
            return
        else:
            print(f"Network '{TARGET_NETWORK}' found (empty).")
    else:
        print(f"Found {len(containers)} containers attached to {TARGET_NETWORK}:")
        for c in containers:
            print(f" - [{c['name']}] (ID: {c['id'][:12]}) using Image: {c['image']}")

    # 2. Confirm Deletion
    print("\nWARNING: This will STOP and REMOVE all listed containers.")
    confirm = input("Proceed with cleanup? (y/n) [n]: ").lower()
    if confirm != 'y':
        print("Cleanup aborted.")
        sys.exit(0)

    # 3. Stop and Remove Containers
    collected_images = set()
    
    if containers:
        print_header("Removing Containers")
        for c in containers:
            print(f"Stopping {c['name']}...")
            run_cmd(f"docker stop {c['id']}")
            
            print(f"Removing {c['name']}...")
            run_cmd(f"docker rm {c['id']}")
            
            # Add image to potential delete list
            collected_images.add(c['image'])

    # 4. Remove Network
    print_header("Removing Network")
    res = run_cmd(f"docker network rm {TARGET_NETWORK}")
    if res:
        print(f"Network '{TARGET_NETWORK}' removed successfully.")
    else:
        print(f"Network '{TARGET_NETWORK}' could not be removed (or already gone).")

    # 5. Optional: Remove Images
    if collected_images:
        print_header("Image Cleanup")
        print("The following images were used by the removed containers:")
        for img in collected_images:
            print(f" - {img}")
        
        img_confirm = input("\nDo you want to delete these images to force a fresh build? (y/n) [n]: ").lower()
        if img_confirm == 'y':
            for img in collected_images:
                print(f"Removing image: {img}")
                run_cmd(f"docker rmi {img}")

    # 6. Optional: Prune Volumes (Database Reset)
    print_header("Volume Cleanup (Database Data)")
    print("Do you want to remove unused Docker volumes?")
    print("WARNING: This will permanently delete your PostgreSQL database data and MinIO files.")
    vol_confirm = input("Prune unused volumes? (y/n) [n]: ").lower()
    if vol_confirm == 'y':
        print("Pruning volumes...")
        run_cmd("docker volume prune -f")
        print("Volumes pruned.")

    print_header("Cleanup Complete")
    print("The environment is now a blank slate for installation.")

if __name__ == "__main__":
    # Check for Docker
    if not run_cmd("docker --version"):
        print("Error: Docker is not installed or not running.")
        sys.exit(1)
        
    try:
        cleanup_process()
    except KeyboardInterrupt:
        print("\nCleanup interrupted.")
        sys.exit(0)