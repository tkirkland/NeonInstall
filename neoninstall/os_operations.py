"""
OS Operations Module

This module contains functions for OS-related operations such as
deploying the OS to the ZFS root.
"""

import os
import subprocess
import questionary
from rich.console import Console
from rich.progress import Progress

# Initialize a rich console for colored output
console = Console()

def _extract_filesystem(pool_name: str) -> bool:
    """
    Extract the filesystem.squashfs to the ZFS root.

    Args:
        pool_name (str): Name of the ZFS pool

    Returns:
        bool: True if extraction was successful, False otherwise
    """
    try:
        # This assumes the squashfs file is in the current directory
        # In a real scenario, you might need to download it or locate it
        squashfs_path = questionary.path(
            "Enter path to filesystem.squashfs:",
            default="./filesystem.squashfs"
        ).ask()

        if not os.path.exists(squashfs_path):
            console.print(f"[bold red]Error:[/bold red] {squashfs_path} not found.")
            return False

        with Progress() as progress:
            task = progress.add_task("[green]Extracting filesystem...", total=100)

            # Use unsquashfs to extract the filesystem
            process = subprocess.Popen(
                ["unsquashfs", "-f", "-d", f"/{pool_name}/ROOT", squashfs_path],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            )

            # Update progress based on output
            for line in process.stdout:
                if "%" in line:
                    try:
                        percent = int(line.split("%")[0].split()[-1])
                        progress.update(task, completed=percent)
                    except (ValueError, IndexError):
                        pass

            process.wait()
            if process.returncode != 0:
                console.print("[bold red]Error:[/bold red] Failed to extract filesystem.")
                return False

        return True
    except (IOError, subprocess.CalledProcessError) as e:
        console.print(f"[bold red]Error:[/bold red] Failed to extract filesystem: {e}")
        return False


def _generate_fstab(pool_name: str, efi_partition: str) -> bool:
    """
    Generate /etc/fstab file.

    Args:
        pool_name (str): Name of the ZFS pool
        efi_partition (str): Path to the EFI partition

    Returns:
        bool: True if fstab generation was successful, False otherwise
    """
    try:
        fstab_content = f"""# /etc/fstab: static file system information.
# Use 'blkid' to print the universally unique identifier for a
# device; this may be used with UUID= as a more robust way to name devices
# that works even if disks are added and removed.

# <file system>                           <mount point>  <type>  <options>  <dump>  <pass>
{efi_partition}                           /boot/efi      vfat    defaults   0       1
/{pool_name}/swap/swapfile                none           swap    sw         0       0
"""

        with open(f"/{pool_name}/ROOT/etc/fstab", "w") as f:
            f.write(fstab_content)

        return True
    except IOError as e:
        console.print(f"[bold red]Error:[/bold red] Failed to generate fstab: {e}")
        return False


def _configure_bootloader(pool_name: str) -> bool:
    """
    Install and configure GRUB bootloader.

    Args:
        pool_name (str): Name of the ZFS pool

    Returns:
        bool: True if bootloader configuration was successful, False otherwise
    """
    try:
        # Install ZFS in the chroot
        chroot_cmd = [
            "chroot", f"/{pool_name}/ROOT",
            "apt-get", "update"
        ]
        subprocess.run(chroot_cmd, check=True)

        chroot_cmd = [
            "chroot", f"/{pool_name}/ROOT",
            "apt-get", "install", "-y", "zfsutils-linux", "grub-efi-amd64"
        ]
        subprocess.run(chroot_cmd, check=True)

        # Configure GRUB for ZFS
        with open(f"/{pool_name}/ROOT/etc/default/grub", "a") as f:
            f.write("\n# ZFS specific settings\n")
            f.write('GRUB_CMDLINE_LINUX_DEFAULT="quiet splash root=ZFS=' + f"{pool_name}/ROOT" + '"\n')

        # Install GRUB
        chroot_cmd = [
            "chroot", f"/{pool_name}/ROOT",
            "grub-install", "--target=x86_64-efi", "--efi-directory=/boot/efi", 
            "--bootloader-id=ubuntu", "--recheck"
        ]
        subprocess.run(chroot_cmd, check=True)

        # Update GRUB
        chroot_cmd = [
            "chroot", f"/{pool_name}/ROOT",
            "update-grub"
        ]
        subprocess.run(chroot_cmd, check=True)

        # Rebuild initramfs
        chroot_cmd = [
            "chroot", f"/{pool_name}/ROOT",
            "update-initramfs", "-u", "-k", "all"
        ]
        subprocess.run(chroot_cmd, check=True)

        return True
    except (IOError, subprocess.CalledProcessError) as e:
        console.print(f"[bold red]Error:[/bold red] Failed to configure bootloader: {e}")
        return False


def deploy_os(pool_name: str, efi_partition: str) -> bool:
    """
    Deploy the OS to the ZFS root.

    Args:
        pool_name (str): Name of the ZFS pool
        efi_partition (str): Path to the EFI partition

    Returns:
        bool: True if OS deployment was successful, False otherwise
    """
    try:
        # Mount the ZFS datasets
        subprocess.run(["zfs", "mount", "-a"], check=True)

        # Create mount point for EFI partition
        os.makedirs(f"/{pool_name}/ROOT/boot/efi", exist_ok=True)

        # Mount EFI partition
        subprocess.run(["mount", efi_partition, f"/{pool_name}/ROOT/boot/efi"], check=True)

        # Extract filesystem
        if not _extract_filesystem(pool_name):
            console.print("[bold red]Error:[/bold red] Failed to extract filesystem.")
            return False

        # Generate fstab
        if not _generate_fstab(pool_name, efi_partition):
            console.print("[bold yellow]Warning:[/bold yellow] Failed to generate fstab, but continuing with installation.")

        # Prepare for chroot
        for mount in ["/dev", "/proc", "/sys"]:
            subprocess.run(["mount", "--bind", mount, f"/{pool_name}/ROOT{mount}"], check=True)

        # Configure bootloader
        if not _configure_bootloader(pool_name):
            console.print("[bold red]Error:[/bold red] Failed to configure bootloader.")
            return False

        console.print("[bold green]OS deployed successfully.[/bold green]")
        return True
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error:[/bold red] Failed to deploy OS: {e}")
        return False
    finally:
        # Cleanup mounts
        for mount in ["/sys", "/proc", "/dev"]:
            try:
                subprocess.run(["umount", f"/{pool_name}/ROOT{mount}"], check=False)
            except:
                pass
