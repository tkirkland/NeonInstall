"""
Disk Operations Module

This module contains functions for disk-related operations such as
selecting disks and creating ZFS pools.
"""

import json
import os
import re
import subprocess
from typing import Any, Dict, List, Tuple

import questionary
from rich.console import Console
from rich.table import Table

# Initialize a rich console for colored output
console = Console()

# Constants
DISK_PATH_PREFIX = "/dev/"
NVME_PREFIX = "nvme"
UNKNOWN_MODEL = "Unknown"
NONE_FS = "None"


def select_disks() -> List[str]:
    """
    Prompt user to select NVMe disks for installation.

    Returns:
        List[str]: List of selected disk paths
    """
    available_disks = get_available_nvme_disks()
    if not available_disks:
        console.print("[bold red]Error:[/bold red] No NVMe disks found.")
        return []

    selected_disks = prompt_for_disk_selection(available_disks)
    if not selected_disks:
        console.print("No disks selected.")
        return []

    disks_with_filesystems = identify_disks_with_filesystems(selected_disks)
    if disks_with_filesystems and not handle_existing_filesystems(
        disks_with_filesystems):
        return []

    return selected_disks


def get_disk_size(disk_path: str) -> str:
    """Get the size of a disk in human-readable format"""
    try:
        size_output = run_command(["lsblk", "-d", "-b", "-o", "SIZE", disk_path])
        if size_output.strip():
            size_bytes = int(size_output.strip().split('\n')[1])
            return f"{size_bytes / (1024**3):.1f}G"
    except (subprocess.SubprocessError, ValueError, IndexError):
        pass
    return "Unknown"


def get_disk_model(disk_path: str) -> str:
    """Get the model name of a disk"""
    try:
        model_output = run_command(["lsblk", "-d", "-o", "MODEL", disk_path])
        if model_output.strip():
            return model_output.strip().split('\n')[1].strip()
    except (subprocess.SubprocessError, IndexError):
        pass
    return UNKNOWN_MODEL


def get_disk_filesystems(disk_path: str) -> Dict[str, str]:
    """Get filesystem information for all partitions on a disk"""
    filesystems = {}
    try:
        parts_output = run_command(["lsblk", "-n", "-o", "NAME,FSTYPE", disk_path])
        for line in parts_output.strip().split('\n'):
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1].strip():
                fs_type = parts[1].strip()
                part_name = f"/dev/{parts[0].strip()}"
                if fs_type == "ntfs":
                    fs_type = "ntfs (Windows)"
                filesystems[part_name] = fs_type
    except subprocess.SubprocessError:
        pass
    return filesystems


def format_filesystem_description(filesystems: Dict[str, str]) -> str:
    """Format filesystem information into a readable string"""
    if not filesystems:
        return ""
    return ", ".join([f"{os.path.basename(p)}: {fs}" for p, fs in filesystems.items()])


def get_available_nvme_disks() -> List[Dict[str, Any]]:
    """
    Get a list of available NVMe disks with their details.

    Returns:
        List[Dict[str, Any]]: List of disk info dictionaries
    """
    nvme_disks = []

    try:
        # Get NVMe devices and sort them naturally
        nvme_devices = [d for d in os.listdir('/dev') if d.startswith(NVME_PREFIX) and re.match(r'nvme\d+n\d+$', d)]
        nvme_devices.sort(key=lambda x: [int(n) for n in re.findall(r'\d+', x)])

        for device in nvme_devices:
            disk_path = f"{DISK_PATH_PREFIX}{device}"

            # Get disk information
            size = get_disk_size(disk_path)
            model = get_disk_model(disk_path)
            filesystems = get_disk_filesystems(disk_path)
            fs_desc = format_filesystem_description(filesystems)

            # Basic disk information
            basic_info = f"{disk_path} ({size}, {model})"

            # Create display info with Rich formatting
            display_info = basic_info
            if filesystems:
                display_info += f" - [red]Has filesystem(s): {fs_desc}[/red]"
            else:
                display_info += f" - [green]No formatted partitions[/green]"

            # Create clean disk info without Rich formatting
            clean_info = basic_info
            if filesystems:
                clean_info += f" - Has filesystem(s): {fs_desc}"
            else:
                clean_info += " - No formatted partitions"

            # Create the disk info dictionary
            disk_info = {
                "name": clean_info,
                "value": disk_path,
                "display": display_info,
                "size": size,
                "model": model,
                "filesystems": filesystems
            }
            nvme_disks.append(disk_info)

    except (OSError, subprocess.SubprocessError) as e:
        console.print(f"[bold red]Error:[/bold red] Failed to list disks: {e}")
        return []

    if not nvme_disks:
        console.print("[bold red]Error:[/bold red] No NVMe disks found.")

    return nvme_disks


def get_filesystem_info(disk_path: str) -> Dict[str, str]:
    """
    Get filesystem information for a disk and all its partitions.

    Args:
        disk_path: Path to the disk

    Returns:
        Dict[str, str]: Dictionary mapping partition paths to filesystem types
    """
    fs_info = {}

    try:
        # Get all partitions for this disk
        lsblk_output = run_command([
            "lsblk", "-o", "NAME,KNAME,FSTYPE", "-J", "-p", disk_path
        ])

        try:
            device_data = json.loads(lsblk_output)
        except json.JSONDecodeError:
            return fs_info

        if 'blockdevices' not in device_data or not device_data['blockdevices']:
            return fs_info

        # Process the disk and its children (partitions)
        device = device_data['blockdevices'][0]

        # Check if the main disk has a filesystem
        if 'fstype' in device and device['fstype']:
            fs_info[device['kname']] = device['fstype']

        # Check all partitions
        if 'children' in device:
            for partition in device['children']:
                if 'fstype' in partition and partition['fstype']:
                    fs_info[partition['kname']] = partition['fstype']

    except (subprocess.SubprocessError, KeyError, IndexError) as e:
        console.print(
            f"[bold yellow]Warning:[/bold yellow] Failed to get filesystem info for {disk_path}: {e}")

    return fs_info




def prompt_for_disk_selection(available_disks: List[Dict[str, Any]]) -> List[str]:
    """
    Prompt the user to select disks from the available options.

    Args:
        available_disks: List of available disk info dictionaries

    Returns:
        List[str]: List of selected disk paths
    """
    # First display the disk info with Rich formatting
    console.print("\nAvailable NVMe disks:")
    for i, disk in enumerate(available_disks):
        console.print(f"{i+1}. {disk['display']}")

    console.print()  # Add a blank line for better readability

    # Then use questionary with clean text
    return questionary.checkbox(
        "Select NVMe disks for installation:",
        choices=[{"name": disk["name"], "value": disk["value"]} for disk in available_disks]
    ).ask()


def identify_disks_with_filesystems(disks: List[str]) -> List[str]:
    """
    Identify which of the selected disks have existing filesystems.

    Args:
        disks: List of disk paths

    Returns:
        List[str]: List of disk paths that have filesystems
    """
    disks_with_fs = []

    for disk in disks:
        fs_info = get_filesystem_info(disk)
        if fs_info:
            disks_with_fs.append(disk)

    return disks_with_fs


def handle_existing_filesystems(disks_with_fs: List[str]) -> bool:
    """
    Handle disks with existing filesystems by prompting the user and wiping if confirmed.

    Args:
        disks_with_fs: List of disk paths with existing filesystems

    Returns:
        bool: True if handled successfully, False otherwise
    """
    console.print(
        "[bold yellow]Warning:[/bold yellow] The following disks have existing filesystems:")

    # Show detailed filesystem information for each disk
    for disk in disks_with_fs:
        console.print(f"  - {disk}")
        fs_info = get_filesystem_info(disk)
        for part, fs_type in fs_info.items():
            console.print(f"    {part}: {fs_type}")

    if questionary.confirm(
        "Do you want to wipe these disks? [THIS WILL DESTROY ALL DATA]").ask():
        if wipe_disks(disks_with_fs):
            console.print("[bold green]Disks wiped successfully.[/bold green]")
            return True
        return False
    else:
        console.print("Aborting installation.")
        return False


def wipe_disks(disks: List[str]) -> bool:
    """
    Wipe the specified disks.

    Args:
        disks: List of disk paths to wipe

    Returns:
        bool: True if all disks were wiped successfully, False otherwise
    """
    for disk in disks:
        try:
            console.print(f"Wiping disk {disk}...")

            # First attempt to wipe any existing partition table signatures using wipefs
            try:
                run_command(["wipefs", "--all", disk])
            except subprocess.SubprocessError as e:
                console.print(
                    f"[bold yellow]Warning:[/bold yellow] Failed to run wipefs on {disk}: {e}")

            # Then use sgdisk to completely wipe the partition table
            run_command(["sgdisk", "--zap-all", disk])

            # Sync to ensure changes are written
            run_command(["sync"])

        except subprocess.SubprocessError as e:
            console.print(
                f"[bold red]Error:[/bold red] Failed to wipe disk {disk}: {e}")
            return False
    return True


def run_command(command: List[str]) -> str:
    """
    Run a shell command and return its output.

    Args:
        command: Command to run as a list of strings

    Returns:
        str: Command output

    Raises:
        subprocess.CalledProcessError: If the command fails
    """
    try:
        result = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        # Include stderr in the error message for better debugging
        error_message = f"Command {' '.join(command)} failed with error: {e.stderr}"
        raise subprocess.CalledProcessError(e.returncode, e.cmd, e.output,
                                            e.stderr) from e


def _create_trim_service_files(pool_name: str) -> bool:
    """
    Create systemd service files for periodic TRIM on the ZFS pool.

    Args:
        pool_name (str): Name of the ZFS pool

    Returns:
        bool: True if service files were created successfully, False otherwise
    """
    try:
        # Create TRIM timer service
        trim_timer = """[Unit]
Description=ZFS TRIM Timer

[Timer]
OnCalendar=weekly
Persistent=true

[Install]
WantedBy=timers.target
"""

        timer_path = "/etc/systemd/system/zfs-trim.timer"
        with open(timer_path, "w") as f:
            f.write(trim_timer)

        # Create a TRIM service
        trim_service = """[Unit]
Description=ZFS TRIM Service
Requires=zfs.target

[Service]
Type=oneshot
ExecStart=/usr/sbin/zpool trim """ + pool_name + """

[Install]
WantedBy=multi-user.target
"""

        service_path = "/etc/systemd/system/zfs-trim.service"
        with open(service_path, "w") as f:
            f.write(trim_service)

        # Enable the timer
        subprocess.run(["systemctl", "enable", "zfs-trim.timer"], check=True)

        return True
    except (IOError, subprocess.CalledProcessError) as e:
        console.print(
            f"[bold red]Error:[/bold red] Failed to create TRIM service files: {e}")
        return False


def create_zfs_pool(disks: List[str]) -> Tuple[bool, str, str]:
    """
    Create a ZFS pool on the selected disks.

    Args:
        disks (List[str]): List of disk paths

    Returns:
        Tuple[bool, str, str]: A tuple containing:
            - success: True if pool creation was successful, False otherwise
            - pool_name: Name of the created pool (empty string if failed)
            - efi_partition: Path to the EFI partition (empty string if failed)
    """
    # Get pool configuration from a user
    pool_type, pool_name = _get_pool_configuration(disks)

    # Prepare disk partitions
    success, efi_partition = _prepare_disk_partitions(disks)
    if not success:
        return False, "", ""

    # Create the ZFS pool
    zfs_partitions = [f"{disk}2" for disk in disks]
    pool_create_cmd = _build_pool_create_command(pool_type, pool_name, disks,
                                                 zfs_partitions)

    try:
        console.print(f"Creating ZFS pool with command: {' '.join(pool_create_cmd)}")
        run_command(pool_create_cmd)
        console.print(
            f"[bold green]ZFS pool '{pool_name}' created successfully.[/bold green]")

        # Configure pool options
        if not configure_pool_options(pool_name):
            return False, "", ""

        return True, pool_name, efi_partition
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error:[/bold red] Failed to create ZFS pool: {e}")
        return False, "", ""


def _get_pool_configuration(disks: List[str]) -> Tuple[str, str]:
    """Get pool type and name from user input."""
    pool_types = _get_available_pool_types(len(disks))

    # Prompt user to select a pool type
    pool_type = questionary.select(
        "Select ZFS pool type:",
        choices=pool_types
    ).ask()

    # Prompt for pool name
    pool_name = questionary.text(
        "Enter ZFS pool name:",
        default="neonpool"
    ).ask()

    return pool_type, pool_name


def _get_available_pool_types(disk_count: int) -> List[Dict[str, str]]:
    """Determine available pool types based on disk count."""
    if disk_count == 1:
        return [{"name": "Single disk (no redundancy)", "value": "single"}]
    elif disk_count == 2:
        return [
            {"name": "Mirror (RAID1, 50% usable space)", "value": "mirror"},
            {"name": "Single disk (no redundancy, use second disk for separate pool)",
             "value": "single"}
        ]
    else:  # disk_count >= 3
        pool_types = [
            {"name": f"RAIDZ1 (RAID5, {disk_count - 1}/{disk_count} usable space)",
             "value": "raidz1"},
            {"name": "Mirror (RAID1, 50% usable space)", "value": "mirror"},
            {"name": "Single disk (no redundancy, use other disks for separate pools)",
             "value": "single"}
        ]
        if disk_count >= 4:
            pool_types.insert(1, {
                "name": f"RAIDZ2 (RAID6, {disk_count - 2}/{disk_count} usable space)",
                "value": "raidz2"})
        return pool_types


def _prepare_disk_partitions(disks: List[str]) -> Tuple[bool, str]:
    """Create partitions on each disk and format EFI partition on the first disk."""
    for disk in disks:
        try:
            # First wipe the disk completely to ensure clean state
            run_command(["wipefs", "--all", disk])

            # Create a GPT partition table
            run_command(["sgdisk", "--zap-all", disk])

            # Create EFI partition (1024 MB)
            run_command([
                "sgdisk", "--new=1:0:+1024M", "--typecode=1:EF00",
                "--change-name=1:EFI", disk
            ])

            # Create ZFS partition (rest of disk)
            run_command([
                "sgdisk", "--new=2:0:0", "--typecode=2:BF01",
                "--change-name=2:ZFS", disk
            ])

            # Force kernel to re-read partition table
            try:
                run_command(["partprobe", disk])
            except subprocess.CalledProcessError:
                # If partprobe fails, try the old-school method
                try:
                    run_command(["blockdev", "--rereadpt", disk])
                except subprocess.CalledProcessError:
                    # If both fail, warn but continue
                    console.print(
                        f"[bold yellow]Warning:[/bold yellow] Failed to reread partition table on {disk}")

            # Sync to ensure changes are written
            run_command(["sync"])

        except subprocess.CalledProcessError as e:
            console.print(
                f"[bold red]Error:[/bold red] Failed to create partitions on {disk}: {e}")
            return False, ""

    # Allow system time to recognize new partitions
    import time
    time.sleep(2)

    # Format EFI partition on the first disk
    efi_partition = f"{disks[0]}1"

    # Wait for the partition to be available
    max_retries = 5
    for attempt in range(max_retries):
        if os.path.exists(efi_partition):
            break
        console.print(
            f"Waiting for EFI partition {efi_partition} to appear (attempt {attempt + 1}/{max_retries})...")
        time.sleep(2)

    if not os.path.exists(efi_partition):
        console.print(
            f"[bold red]Error:[/bold red] EFI partition {efi_partition} was not created.")
        return False, ""

    try:
        run_command(["mkfs.fat", "-F32", "-n", "EFI", efi_partition])
        return True, efi_partition
    except subprocess.CalledProcessError as e:
        console.print(
            f"[bold red]Error:[/bold red] Failed to format EFI partition: {e}")
        return False, ""


def _build_pool_create_command(pool_type: str, pool_name: str, disks: List[str],
                               zfs_partitions: List[str]) -> List[str]:
    """Build the zpool create a command based on a pool type."""
    pool_create_cmd = ["zpool", "create", "-f"]

    # Add a pool type and disks
    if pool_type == "single":
        if len(disks) == 1:
            pool_create_cmd.extend([pool_name, zfs_partitions[0]])
        else:
            # For single type with multiple disks, only use the first disk
            pool_create_cmd.extend([pool_name, zfs_partitions[0]])
            console.print(
                "[bold yellow]Warning:[/bold yellow] Only using the first disk for the ZFS pool.")
    elif pool_type == "mirror":
        pool_create_cmd.extend([pool_name, "mirror"] + zfs_partitions)
    elif pool_type == "raidz1":
        pool_create_cmd.extend([pool_name, "raidz"] + zfs_partitions)
    elif pool_type == "raidz2":
        pool_create_cmd.extend([pool_name, "raidz2"] + zfs_partitions)

    # Add ZFS pool options
    pool_create_cmd.extend([
        "-o", "ashift=12",
        "-o", "compression=zstd",
        "-o", "xattr=sa",
        "-o", "acltype=posixacl",
        "-o", "dnodesize=auto",
        "-o", "atime=off",
        "-O", "canmount=off",
        "-O", "mountpoint=none",
        "-O", "normalization=formD"
    ])

    return pool_create_cmd


def configure_pool_options(pool_name: str) -> bool:
    """
    Configure additional pool options after pool creation.

    Args:
        pool_name (str): Name of the ZFS pool to configure

    Returns:
        bool: True if all configurations were successful, False otherwise
    """
    success = True

    if not enable_pool_autotrim(pool_name):
        console.print(
            "[bold yellow]Warning:[/bold yellow] Failed to enable autotrim, but continuing.")
        success = False

    if not _create_trim_service_files(pool_name):
        console.print(
            "[bold yellow]Warning:[/bold yellow] Failed to create TRIM service files, but continuing.")
        success = False

    return success


def enable_pool_autotrim(pool_name: str) -> bool:
    """
    Enable TRIM on the specified ZFS pool.

    Args:
        pool_name (str): Name of the ZFS pool

    Returns:
        bool: True if TRIM was enabled successfully, False otherwise
    """
    try:
        run_command(["zpool", "set", "autotrim=on", pool_name])
        return True
    except subprocess.CalledProcessError as e:
        console.print(f"[bold yellow]Warning:[/bold yellow] Failed to enable TRIM: {e}")
        return False

def display_disk_info(disks: List[Dict[str, Any]]) -> None:
    """
    Display disk information in a formatted table.

    Args:
        disks: List of disk information dictionaries
    """
    table = Table(title="Available NVMe Disks")

    table.add_column("Device", style="cyan")
    table.add_column("Size", style="magenta")
    table.add_column("Model", style="green")
    table.add_column("Filesystems", style="red")

    for disk in disks:
        fs_display = "[green]No formatted partitions[/green]"
        if disk.get('filesystems'):
            fs_parts = []
            for part, fs_type in disk['filesystems'].items():
                part_name = os.path.basename(part)
                fs_parts.append(f"{part_name}: {fs_type}")
            fs_display = "[red]" + ", ".join(fs_parts) + "[/red]"

        table.add_row(
            os.path.basename(disk['value']),
            disk['size'],
            disk['model'],
            fs_display
        )

    console.print(table)
