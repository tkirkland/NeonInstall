"""
System Operations Module

This module contains functions for system-level operations such as
checking prerequisites and configuring system settings.
"""

import os
import subprocess
from rich.console import Console

# Initialize a rich console for colored output
console = Console()

def check_prerequisites() -> bool:
    """
    Check if all prerequisites are met to run the installer.

    Returns:
        bool: True if all prerequisites are met, False otherwise
    """
    # Check if running as root
    if os.geteuid() != 0:
        console.print("[bold red]Error:[/bold red] This script must be run as root.")
        return False

    # Check if required commands are available
    required_commands = ["zpool", "zfs", "sgdisk", "mkfs.fat", "rsync", "unsquashfs", "chroot"]
    for cmd in required_commands:
        try:
            subprocess.run(["which", cmd], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError:
            console.print(f"[bold red]Error:[/bold red] Required command '{cmd}' not found.")
            return False

    return True

def configure_system_settings(pool_name: str) -> bool:
    """
    Configure system settings like locale, keyboard layout, timezone, hostname, etc.

    Args:
        pool_name (str): Name of the ZFS pool

    Returns:
        bool: True if configuration was successful, False otherwise
    """
    try:
        # Prepare for chroot
        for mount in ["/dev", "/proc", "/sys"]:
            subprocess.run(["mount", "--bind", mount, f"/{pool_name}/ROOT{mount}"], check=True)

        # Set locale to en_US.UTF-8
        with open(f"/{pool_name}/ROOT/etc/locale.gen", "a") as f:
            f.write("en_US.UTF-8 UTF-8\n")

        chroot_cmd = [
            "chroot", f"/{pool_name}/ROOT",
            "locale-gen"
        ]
        subprocess.run(chroot_cmd, check=True)

        with open(f"/{pool_name}/ROOT/etc/default/locale", "w") as f:
            f.write('LANG="en_US.UTF-8"\n')

        # Set keyboard layout to us
        with open(f"/{pool_name}/ROOT/etc/default/keyboard", "w") as f:
            f.write("""XKBMODEL="pc105"
XKBLAYOUT="us"
XKBVARIANT=""
XKBOPTIONS=""
BACKSPACE="guess"
""")

        # Set timezone to America/New_York
        chroot_cmd = [
            "chroot", f"/{pool_name}/ROOT",
            "ln", "-sf", "/usr/share/zoneinfo/America/New_York", "/etc/localtime"
        ]
        subprocess.run(chroot_cmd, check=True)

        # Set hostname to precision
        with open(f"/{pool_name}/ROOT/etc/hostname", "w") as f:
            f.write("precision\n")

        # Set FQDN in /etc/hosts
        with open(f"/{pool_name}/ROOT/etc/hosts", "w") as f:
            f.write("""127.0.0.1       localhost
127.0.1.1       precision.home.tonykirkland.net precision

# The following lines are desirable for IPv6 capable hosts
::1             localhost ip6-localhost ip6-loopback
ff02::1         ip6-allnodes
ff02::2         ip6-allrouters
""")

        # Configure network for DHCP
        netplan_config = """network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:
      dhcp4: true
"""

        os.makedirs(f"/{pool_name}/ROOT/etc/netplan", exist_ok=True)
        with open(f"/{pool_name}/ROOT/etc/netplan/01-netcfg.yaml", "w") as f:
            f.write(netplan_config)

        console.print("[bold green]System settings configured successfully.[/bold green]")
        return True
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error:[/bold red] Failed to configure system settings: {e}")
        return False
    finally:
        # Cleanup mounts
        for mount in ["/sys", "/proc", "/dev"]:
            try:
                subprocess.run(["umount", f"/{pool_name}/ROOT{mount}"], check=False)
            except:
                pass
