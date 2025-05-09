import os
import subprocess
import sys
from pathlib import Path

from os_operations import console

# Constants for system configuration
SYSTEM_MOUNTS = ["/dev", "/proc", "/sys"]
DEFAULT_LOCALE = "en_US.UTF-8"
DEFAULT_TIMEZONE = "America/New_York"
DEFAULT_HOSTNAME = "precision"
DEFAULT_KEYBOARD_CONFIG = """XKBMODEL="pc105"
XKBLAYOUT="us"
XKBVARIANT=""
XKBOPTIONS=""
BACKSPACE="guess"
"""

DEFAULT_HOSTS_CONFIG = """127.0.0.1       localhost
127.0.1.1       {hostname}.home.tonykirkland.net {hostname}

# The following lines are desirable for IPv6 capable hosts
::1             localhost ip6-localhost ip6-loopback
ff02::1         ip6-allnodes
ff02::2         ip6-allrouters
"""

DEFAULT_NETPLAN_CONFIG = """network:
  version: 2
  renderer: networkd
  ether-nets:
    eth0:
      dhcp4: true
"""

def mount_system_directories(root_path: Path) -> None:
    """Mount system directories for chroot environment."""
    for mount in SYSTEM_MOUNTS:
        subprocess.run(["mount", "--bind", mount, str(root_path / mount[1:])], check=True)

def configure_locale(root_path: Path) -> None:
    """Configure system locale settings."""
    with open(root_path / "etc/locale.gen", "a") as f:
        f.write(f"{DEFAULT_LOCALE} UTF-8\n")

    subprocess.run(["chroot", str(root_path), "locale-gen"], check=True)

    with open(root_path / "etc/default/locale", "w") as f:
        f.write(f'LANG="{DEFAULT_LOCALE}"\n')

def configure_keyboard(root_path: Path) -> None:
    """Configure keyboard layout settings."""
    with open(root_path / "etc/default/keyboard", "w") as f:
        f.write(DEFAULT_KEYBOARD_CONFIG)

def configure_timezone(root_path: Path) -> None:
    """Configure system timezone."""
    subprocess.run([
        "chroot", str(root_path),
        "ln", "-sf", f"/usr/share/zoneinfo/{DEFAULT_TIMEZONE}", "/etc/localtime"
    ], check=True)

def configure_network(root_path: Path) -> None:
    """Configure network settings."""
    netplan_dir = root_path / "etc/netplan"
    os.makedirs(netplan_dir, exist_ok=True)
    with open(netplan_dir / "01-netcfg.yaml", "w") as f:
        f.write(DEFAULT_NETPLAN_CONFIG)

def configure_system_settings(pool_name: str) -> bool:
    """Configure system settings like locale,
    keyboard layout, timezone, hostname, etc."""
    root_path = Path(f"/{pool_name}/ROOT")

    try:
        mount_system_directories(root_path)

        configure_locale(root_path)
        configure_keyboard(root_path)
        configure_timezone(root_path)

        # Configure hostname
        with open(root_path / "etc/hostname", "w") as f:
            f.write(f"{DEFAULT_HOSTNAME}\n")

        # Configure hosts file
        with open(root_path / "etc/hosts", "w") as f:
            f.write(DEFAULT_HOSTS_CONFIG.format(hostname=DEFAULT_HOSTNAME))

        configure_network(root_path)

        console.print("[bold green]System settings configured successfully.[/bold green]")
        return True

    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error:[/bold red] Failed to configure system settings: {e}")
        # Cleanup mounts
        for mount in reversed(SYSTEM_MOUNTS):
            try:
                subprocess.run(["umount", f"/{pool_name}/ROOT{mount}"], check=False)
            except subprocess.SubprocessError:
                sys.exit(1)
        return False
