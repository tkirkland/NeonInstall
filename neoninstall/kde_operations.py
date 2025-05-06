"""
KDE Operations Module

This module contains functions for KDE-specific operations such as
configuring KDE Neon settings.
"""

import os
import subprocess
from rich.console import Console

# Initialize a rich console for colored output
console = Console()

def configure_kde_neon(pool_name: str) -> bool:
    """
    Configure KDE Neon specific settings.

    Args:
        pool_name (str): Name of the ZFS pool

    Returns:
        bool: True if configuration was successful, False otherwise
    """
    try:
        # Add KDE Neon repositories
        neon_repo = """deb http://archive.neon.kde.org/user focal main
deb-src http://archive.neon.kde.org/user focal main
"""

        os.makedirs(f"/{pool_name}/ROOT/etc/apt/sources.list.d", exist_ok=True)
        with open(f"/{pool_name}/ROOT/etc/apt/sources.list.d/neon.list", "w") as f:
            f.write(neon_repo)

        # Prepare for chroot
        for mount in ["/dev", "/proc", "/sys"]:
            subprocess.run(["mount", "--bind", mount, f"/{pool_name}/ROOT{mount}"], check=True)

        # Install and configure SDDM
        chroot_cmd = [
            "chroot", f"/{pool_name}/ROOT",
            "apt-get", "update"
        ]
        subprocess.run(chroot_cmd, check=True)

        chroot_cmd = [
            "chroot", f"/{pool_name}/ROOT",
            "apt-get", "install", "-y", "sddm"
        ]
        subprocess.run(chroot_cmd, check=True)

        # Set SDDM theme to breeze
        sddm_conf = """[Theme]
Current=breeze
"""

        os.makedirs(f"/{pool_name}/ROOT/etc/sddm.conf.d", exist_ok=True)
        with open(f"/{pool_name}/ROOT/etc/sddm.conf.d/theme.conf", "w") as f:
            f.write(sddm_conf)

        # Install KDE packages
        chroot_cmd = [
            "chroot", f"/{pool_name}/ROOT",
            "apt-get", "install", "-y",
            "language-pack-kde-en", "plasma-desktop", "kde-config-gtk-style",
            "plasma-integration"
        ]
        subprocess.run(chroot_cmd, check=True)

        # Enable SDDM
        chroot_cmd = [
            "chroot", f"/{pool_name}/ROOT",
            "systemctl", "enable", "sddm"
        ]
        subprocess.run(chroot_cmd, check=True)

        console.print("[bold green]KDE Neon configured successfully.[/bold green]")
        return True
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error:[/bold red] Failed to configure KDE Neon: {e}")
        return False
    finally:
        # Cleanup mounts
        for mount in ["/sys", "/proc", "/dev"]:
            try:
                subprocess.run(["umount", f"/{pool_name}/ROOT{mount}"], check=False)
            except:
                pass