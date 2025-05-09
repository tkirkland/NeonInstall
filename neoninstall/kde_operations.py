"""
KDE Operations Module

This module contains functions for KDE-specific operations such as
configuring KDE Neon settings.
"""

import os
import subprocess
from typing import List

from rich.console import Console

# Initialize console for output
console = Console()

# Constants for configuration
KDE_NEON_REPO = """deb    http://archive.neon.kde.org/user focal main
deb-src http://archive.neon.kde.org/user focal main
"""

SDDM_THEME_CONFIG = """[Theme]
Current=breeze
"""

KDE_PACKAGES = [
    "language-pack-kde-en",
    "plasma-desktop",
    "kde-config-gtk-style",
    "plasma-integration"
]

MOUNT_POINTS = ["/dev", "/proc", "/sys"]


def configure_kde_neon(pool_name: str) -> bool:
    """
    Configure KDE Neon specific settings.
    Args:
        pool_name (str): Name of the ZFS pool
    Returns:
        bool: True if configuration was successful, False otherwise
    """
    root_path = f"/{pool_name}/ROOT"

    try:
        add_kde_neon_repository(root_path)
        mount_virtual_filesystems(root_path)

        # Perform chroot operations
        run_chroot_command(root_path, ["apt-get", "update"])
        install_sddm(root_path)
        configure_sddm_theme(root_path)
        install_kde_packages(root_path)
        enable_sddm_service(root_path)

        console.print("[bold green]KDE Neon configured successfully.[/bold green]")
        return True
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error:[/bold red] Failed to configure KDE Neon: {e}")
        return False
    finally:
        unmount_virtual_filesystems(root_path)


def add_kde_neon_repository(root_path: str) -> None:
    """Add KDE Neon repositories to apt sources."""
    repo_path = f"{root_path}/etc/apt/sources.list.d"
    os.makedirs(repo_path, exist_ok=True)
    with open(f"{repo_path}/neon.list", "w") as f:
        f.write(KDE_NEON_REPO)


def mount_virtual_filesystems(root_path: str) -> None:
    """Mount virtual filesystems needed for chroot."""
    for mount in MOUNT_POINTS:
        subprocess.run(["mount", "--bind", mount, f"{root_path}{mount}"], check=True)


def unmount_virtual_filesystems(root_path: str) -> None:
    """Unmount virtual filesystems after chroot operations."""
    # Unmount in reverse order for proper dependency handling
    for mount in reversed(MOUNT_POINTS):
        try:
            subprocess.run(["umount", f"{root_path}{mount}"], check=False)
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] Failed to unmount {mount}: {e}")


def run_chroot_command(root_path: str, command: List[str]) -> None:
    """Run a command in a chroot environment."""
    chroot_cmd = ["chroot", root_path] + command
    subprocess.run(chroot_cmd, check=True)


def install_sddm(root_path: str) -> None:
    """Install SDDM display manager."""
    run_chroot_command(root_path, ["apt-get", "install", "-y", "sddm"])


def configure_sddm_theme(root_path: str) -> None:
    """Configure SDDM theme settings."""
    sddm_conf_dir = f"{root_path}/etc/sddm.conf.d"
    os.makedirs(sddm_conf_dir, exist_ok=True)
    with open(f"{sddm_conf_dir}/theme.conf", "w") as f:
        f.write(SDDM_THEME_CONFIG)


def install_kde_packages(root_path: str) -> None:
    """Install essential KDE packages."""
    install_cmd = ["apt-get", "install", "-y"] + KDE_PACKAGES
    run_chroot_command(root_path, install_cmd)


def enable_sddm_service(root_path: str) -> None:
    """Enable SDDM service to start on boot."""
    run_chroot_command(root_path, ["systemctl", "enable", "sddm"])
