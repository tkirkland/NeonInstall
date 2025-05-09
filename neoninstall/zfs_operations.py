"""
ZFS Operations Module

This module contains functions for ZFS-specific operations such as
creating ZFS datasets and configuring ZFS properties.
"""

import subprocess

import psutil
from rich.console import Console

# Initialize a rich console for colored output
console = Console()


def _create_snapshot_service_files(pool_name: str) -> bool:
    """
    Create systemd service files for daily ZFS snapshots.

    Args:
        pool_name (str): Name of the ZFS pool

    Returns:
        bool: True if service files were created successfully, False otherwise
    """
    try:
        # Create snapshot service
        snapshot_service = """[Unit]
Description=ZFS Daily Snapshot Service

[Service]
Type=oneshot
ExecStart=/usr/sbin/zfs snapshot -r """ + pool_name + """/ROOT@daily-$(date +%Y%m%d)
ExecStart=/bin/sh -c 'for snap in $(/usr/sbin/zfs list -t snapshot -o name | grep "@daily-" | sort | head -n -4); do /usr/sbin/zfs destroy $snap; done'

[Install]
WantedBy=multi-user.target
"""

        service_path = "/etc/systemd/system/zfs-snapshot.service"
        with open(service_path, "w") as f:
            f.write(snapshot_service)

        # Create snapshot timer
        snapshot_timer = """[Unit]
Description=ZFS Daily Snapshot Timer

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
"""

        timer_path = "/etc/systemd/system/zfs-snapshot.timer"
        with open(timer_path, "w") as f:
            f.write(snapshot_timer)

        # Enable the timer
        subprocess.run(["systemctl", "enable", "zfs-snapshot.timer"], check=True)

        return True
    except (IOError, subprocess.CalledProcessError) as e:
        console.print(
            f"[bold red]Error:[/bold red] Failed to create snapshot service files: {e}")
        return False


def create_zfs_datasets(pool_name: str) -> bool:
    """
    Create ZFS datasets for the system.

    Args:
        pool_name (str): Name of the ZFS pool

    Returns:
        bool: True if dataset creation was successful, False otherwise
    """
    try:
        # Create root dataset
        subprocess.run([
            "zfs", "create", "-o", "mountpoint=/",
            f"{pool_name}/ROOT"
        ], check=True)

        # Create home dataset
        subprocess.run([
            "zfs", "create", "-o", "mountpoint=/home",
            f"{pool_name}/ROOT/home"
        ], check=True)

        # Create tmp dataset (excluded from snapshots)
        subprocess.run([
            "zfs", "create", "-o", "mountpoint=/tmp", "-o", "com.sun:auto-snapshot=false",
            f"{pool_name}/ROOT/tmp"
        ], check=True)

        # Create var dataset
        subprocess.run([
            "zfs", "create", "-o", "mountpoint=/var",
            f"{pool_name}/ROOT/var"
        ], check=True)

        # Set up automatic snapshots
        if not _create_snapshot_service_files(pool_name):
            console.print(
                "[bold yellow]Warning:[/bold yellow] Failed to create snapshot "
                "service files, but continuing with installation.")

        # Create swap file
        mem_bytes = psutil.virtual_memory().total
        swap_size_mb = int(mem_bytes / (4 * 1024 * 1024))  # 1/4 of RAM in MB

        # Create a dataset for swap with compression disabled
        subprocess.run([
            "zfs", "create", "-o", "compression=off", "-o", "primarycache=metadata",
            "-o", "com.sun:auto-snapshot=false", f"{pool_name}/swap"
        ], check=True)

        # Create swap file
        subprocess.run([
            "dd", "if=/dev/zero", f"of=/{pool_name}/swap/swapfile",
            f"bs=1M", f"count={swap_size_mb}"
        ], check=True)

        # Set permissions and create swap
        subprocess.run(["chmod", "600", f"/{pool_name}/swap/swapfile"], check=True)
        subprocess.run(["mkswap", f"/{pool_name}/swap/swapfile"], check=True)

        console.print("[bold green]ZFS datasets created successfully.[/bold green]")
        return True
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error:[/bold red] Failed to create ZFS datasets: {e}")
        return False
