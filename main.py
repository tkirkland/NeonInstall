"""
Main Module

This module serves as the entry point for the KDE Neon ZFS Installer.
It orchestrates the installation process by calling functions from other modules.
"""

import sys

from rich.console import Console

from neoninstall.disk_operations import create_zfs_pool, select_disks
from neoninstall.kde_operations import configure_kde_neon
from neoninstall.os_operations import deploy_os
from neoninstall.system_operations import check_prerequisites, \
    configure_system_settings
from neoninstall.user_operations import configure_ssh, setup_user
from neoninstall.zfs_operations import create_zfs_datasets

# Initialize a rich console for colored output
console = Console()


def main():
    """
    Main function to run the installer.
    """
    console.print("[bold blue]KDE Neon ZFS Installer[/bold blue]")
    console.print("This script will install KDE Neon on a ZFS root filesystem.")
    console.print(
        "Please make sure you have a backup of any important data before proceeding.")

    # Check prerequisites
    if not check_prerequisites():
        console.print("[bold red]Prerequisites not met. Exiting.[/bold red]")
        return 1

    # Select disks
    disks = select_disks()
    if not disks:
        console.print("[bold red]No disks selected. Exiting.[/bold red]")
        return 1

    # Create ZFS pool
    success, pool_name, efi_partition = create_zfs_pool(disks)
    if not success:
        console.print("[bold red]Failed to create ZFS pool. Exiting.[/bold red]")
        return 1

    # Create ZFS datasets
    if not create_zfs_datasets(pool_name):
        console.print("[bold red]Failed to create ZFS datasets. Exiting.[/bold red]")
        return 1

    # Deploy OS
    if not deploy_os(pool_name, efi_partition):
        console.print("[bold red]Failed to deploy OS. Exiting.[/bold red]")
        return 1

    # Configure KDE Neon
    if not configure_kde_neon(pool_name):
        console.print("[bold red]Failed to configure KDE Neon. Exiting.[/bold red]")
        return 1

    # Set up user
    if not setup_user(pool_name):
        console.print("[bold red]Failed to set up user. Exiting.[/bold red]")
        return 1

    # Configure SSH
    if not configure_ssh(pool_name):
        console.print("[bold red]Failed to configure SSH. Exiting.[/bold red]")
        return 1

    # Configure system settings
    if not configure_system_settings(pool_name):
        console.print(
            "[bold red]Failed to configure system settings. Exiting.[/bold red]")
        return 1

    console.print("[bold green]Installation completed successfully![/bold green]")
    console.print("You can now reboot into your new KDE Neon system.")
    console.print("Username: me")
    console.print("Password: changeme")
    console.print(
        "[bold yellow]Don't forget to change the password after first login![/bold yellow]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
