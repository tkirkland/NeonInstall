"""
Disk Operations Module

This module contains functions for disk-related operations such as
selecting disks and creating ZFS pools.
"""

import subprocess
from typing import Any, Dict, List, Optional, Tuple

import questionary
from rich.console import Console

# Initialize a rich console for colored output
console = Console()

# Constants
LSBLK_DISK_FIELDS = ["NAME", "SIZE", "MODEL", "FSTYPE"]
LSBLK_PARTITION_FIELDS = ["FSTYPE"]
NVME_PREFIX = "nvme"
DISK_PATH_PREFIX = "/dev/"
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
    return []

  selected_disks = prompt_for_disk_selection(available_disks)
  if not selected_disks:
    return []

  disks_with_filesystems = identify_disks_with_filesystems(selected_disks)
  if disks_with_filesystems and not handle_existing_filesystems(
      disks_with_filesystems):
    return []

  return selected_disks


def get_available_nvme_disks() -> List[Dict[str, Any]]:
  """
  Get a list of available NVMe disks with their details.

  Returns:
      List[Dict[str, Any]]: List of disk info dictionaries with 'name' and 'value' keys
  """
  nvme_disks = []
  try:
    lsblk_output = run_command(
      ["lsblk", "-d", "-n", "-o", ",".join(LSBLK_DISK_FIELDS)]
    )

    for line in lsblk_output.splitlines():
      disk_info = parse_disk_info(line)
      if disk_info:
        nvme_disks.append(disk_info)

  except subprocess.CalledProcessError as e:
    console.print(f"[bold red]Error:[/bold red] Failed to list disks: {e}")
    return []

  if not nvme_disks:
    console.print("[bold red]Error:[/bold red] No NVMe disks found.")

  return nvme_disks


def parse_disk_info(line: str) -> Optional[Dict[str, str]]:
  """
  Parse disk information from a line of lsblk output.

  Args:
      line: A line from lsblk output

  Returns:
      Optional[Dict[str, str]]: Disk information dictionary or None if not an NVMe disk
  """
  parts = line.split()
  if len(parts) >= 2 and parts[0].startswith(NVME_PREFIX):
    disk_name = parts[0]
    disk_size = parts[1]
    disk_model = " ".join(parts[2:-1]) if len(parts) > 3 else UNKNOWN_MODEL
    fs_type = parts[-1] if len(parts) > 2 else NONE_FS

    disk_path = f"{DISK_PATH_PREFIX}{disk_name}"
    disk_info = f"{disk_path} ({disk_size}, {disk_model})"

    if fs_type != NONE_FS:
      disk_info += f" - [red]Has filesystem: {fs_type}[/red]"

    return {"name": disk_info, "value": disk_path}
  return None


def prompt_for_disk_selection(available_disks: List[Dict[str, Any]]) -> List[str]:
  """
  Prompt the user to select disks from the available options.

  Args:
      available_disks: List of available disk info dictionaries

  Returns:
      List[str]: List of selected disk paths
  """
  return questionary.checkbox(
    "Select NVMe disks for installation:",
    choices=available_disks
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
    try:
      fs_output = run_command(
        ["lsblk", "-n", "-o", ",".join(LSBLK_PARTITION_FIELDS), disk]
      )

      for line in fs_output.splitlines():
        if line.strip() and line.strip() != NONE_FS:
          disks_with_fs.append(disk)
          break
    except subprocess.CalledProcessError:
      pass

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
  for disk in disks_with_fs:
    console.print(f"  - {disk}")

  if questionary.confirm("Do you want to wipe these disks?").ask():
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
      run_command(["sgdisk", "--zap-all", disk])
    except subprocess.CalledProcessError as e:
      console.print(f"[bold red]Error:[/bold red] Failed to wipe disk {disk}: {e}")
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
  result = subprocess.run(
    command,
    check=True,
    stdout=subprocess.PIPE,
    text=True
  )
  return result.stdout


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
    subprocess.run(pool_create_cmd, check=True)
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
      # Create a GPT partition table
      subprocess.run(["sgdisk", "--zap-all", disk], check=True)

      # Create EFI partition (1024 MB)
      subprocess.run([
        "sgdisk", "--new=1:0:+1024M", "--typecode=1:EF00",
        "--change-name=1:EFI", disk
      ], check=True)

      # Create ZFS partition (rest of disk)
      subprocess.run([
        "sgdisk", "--new=2:0:0", "--typecode=2:BF01",
        "--change-name=2:ZFS", disk
      ], check=True)
    except subprocess.CalledProcessError as e:
      console.print(
        f"[bold red]Error:[/bold red] Failed to create partitions on {disk}: {e}")
      return False, ""

  # Format EFI partition on the first disk
  efi_partition = f"{disks[0]}1"
  try:
    subprocess.run(["mkfs.fat", "-F32", "-n", "EFI", efi_partition], check=True)
    return True, efi_partition
  except subprocess.CalledProcessError as e:
    console.print(f"[bold red]Error:[/bold red] Failed to format EFI partition: {e}")
    return False, ""


def _build_pool_create_command(pool_type: str, pool_name: str, disks: List[str],
                               # Create ZFS pool
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
    subprocess.run(["zpool", "set", "autotrim=on", pool_name], check=True)
    return True
  except subprocess.CalledProcessError as e:
    console.print(f"[bold yellow]Warning:[/bold yellow] Failed to enable TRIM: {e}")
    return False
