"""
System Operations Module

This module contains functions for system-level operations such as
checking prerequisites and configuring system settings.
"""

import os
import platform
import subprocess
import sys

from rich.console import Console

# Initialize a rich console for colored output
console = Console()

# Mapping of commands to their corresponding packages
COMMAND_TO_PACKAGE = {
    "zpool": "zfsutils-linux",
    "zfs": "zfsutils-linux",
    "sgdisk": "gdisk",
    "mkfs.fat": "dosfstools",
    "rsync": "rsync",
    "unsquashfs": "squashfs-tools",
    "chroot": "coreutils"
}

# List of required commands
REQUIRED_COMMANDS = ["zpool", "zfs", "sgdisk", "mkfs.fat", "rsync", "unsquashfs",
                    "chroot"]


def check_system_compatibility() -> bool:
    """
    Check if the system is Linux.

    Returns:
        bool: True if the system is Linux, False otherwise
    """
    if platform.system() != "Linux":
        console.print(
            "[bold red]Error:[/bold red] This script is only compatible with Linux.")
        sys.exit(1)
    return True


def check_root_privileges() -> bool:
    """
    Check if the script is running with root privileges.

    Returns:
        bool: True if running as root, False otherwise
    """
    if os.geteuid() != 0:
        console.print("[bold red]Error:[/bold red] This script must be run as root.")
        return False
    return True


def find_missing_commands() -> list:
    """
    Check which required commands are missing.

    Returns:
        list: List of missing commands
    """
    missing_commands = []
    for cmd in REQUIRED_COMMANDS:
        try:
            subprocess.run(["which", cmd], check=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
        except subprocess.CalledProcessError:
            console.print(
                f"[bold yellow]Warning:[/bold yellow] Required command '{cmd}' not found. Attempting to install...")
            missing_commands.append(cmd)
    return missing_commands


def install_packages(missing_commands: list) -> bool:
    """
    Install packages for missing commands.

    Args:
        missing_commands (list): List of missing commands

    Returns:
        bool: True if installation was successful, False otherwise
    """
    # Use a set to eliminate duplicate packages
    packages_to_install = list(
        set(COMMAND_TO_PACKAGE[cmd] for cmd in missing_commands))
    try:
        console.print(f"Installing packages: {', '.join(packages_to_install)}")
        subprocess.run(["apt", "update"], check=True)
        subprocess.run(["apt", "install", "-y"] + packages_to_install, check=True)
        return True
    except subprocess.CalledProcessError as e:
        console.print(
            f"[bold red]Error:[/bold red] Failed to install required packages: {e}")
        return False


def verify_installation(missing_commands: list) -> bool:
    """
    Verify that all commands are now available after installation.

    Args:
        missing_commands (list): List of commands that were missing

    Returns:
        bool: True if all commands are now available, False otherwise
    """
    for cmd in missing_commands:
        try:
            subprocess.run(["which", cmd], check=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
            console.print(
                f"[bold green]Success:[/bold green] Command '{cmd}' is now available.")
        except subprocess.CalledProcessError:
            console.print(
                f"[bold red]Error:[/bold red] Failed to install command '{cmd}'.")
            return False
    return True


def check_prerequisites() -> bool:
    """
    Check if all prerequisites are met to run the installer.
    If a required command is missing, attempt to install the associated package.

    Returns:
        bool: True if all prerequisites are met, False otherwise
    """
    # Check system compatibility
    check_system_compatibility()

    # Check root privileges
    if not check_root_privileges():
        return False

    # Find missing commands
    missing_commands = find_missing_commands()

    # Install packages for missing commands
    if missing_commands:
        if not install_packages(missing_commands):
            return False

        # Verify installation
        if not verify_installation(missing_commands):
            return False

    return True


def configure_system_settings(pool_name: str) -> bool:
    """
    Configure system settings like locale, keyboard layout, timezone, hostname, etc.

    Args:
        pool_name (str): Name of the ZFS pool

    # Returns:
        bool: True if configuration was successful, False otherwise
    """
    try:
        # Prepare for chroot
        for mount in ["/dev", "/proc", "/sys"]:
            subprocess.run(["mount", "--bind", mount, f"/{pool_name}/ROOT{mount}"],
                            check=True)

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

        # Set the keyboard layout to us
        with open(f"/{pool_name}/ROOT/etc/default/keyboard", "w") as f:
            f.write("""XKBMODEL="pc105"
XKBLAYOUT="us"
XKBVARIANT=""
XKBOPTIONS=""
BACKSPACE="guess"
""")

        # Set a timezone to America/New_York
        chroot_cmd = [
            "chroot", f"/{pool_name}/ROOT",
            "ln", "-sf", "/usr/share/zoneinfo/America/New_York", "/etc/localtime"
        ]
        subprocess.run(chroot_cmd, check=True)

        # Set the hostname to precision
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

        # Configure a network for DHCP
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

        console.print(
            "[bold green]System settings configured successfully.[/bold green]")
        return True
    except subprocess.CalledProcessError as e:
        console.print(
            f"[bold red]Error:[/bold red] Failed to configure system settings: {e}")
        # Cleanup mounts
        for mount in ["/sys", "/proc", "/dev"]:
            try:
                subprocess.run(["umount", f"/{pool_name}/ROOT{mount}"], check=False)
            except IOError:
                return False
    return False

