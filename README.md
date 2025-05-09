# KDE Neon ZFS Installer

A Python installer script that replicates the functionality of Calamares but builds a
KDE Neon system on a ZFS root using modern best practices and strict security
defaults.

## Features

- **ZFS Root**: Installs KDE Neon on a ZFS root filesystem with modern best practices
- **Secure Defaults**: Implements strict security defaults for SSH and system
  configuration
- **User-Friendly**: Interactive prompts guide you through the installation process
- **Flexible Disk Configuration**: Supports various ZFS pool types based on the
  number of disks
- **Automated Setup**: Handles all aspects of installation from disk partitioning to
  user setup
- **Modular Design**: Code is organized into logical modules for better
  maintainability

## Requirements

### System Requirements

- Linux system with root access
- NVMe disk(s) for installation
- Internet connection for package installation
- KDE Neon squashfs image

### Required Commands

The following commands must be available on the system:

- zpool, zfs
- sgdisk
- mkfs.fat
- rsync
- unsquashfs
- chroot

### Python Dependencies

- Python 3.13+
- pyyaml
- questionary
- psutil
- rich

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/neon-zfs-installer.git
   cd neon-zfs-installer
   ```

2. Install dependencies using Poetry:
   ```
   poetry install
   ```

3. Run the installer with root privileges:
   ```
   sudo poetry run python neon_zfs_installer.py
   ```

## Usage

The installer will guide you through the following steps:

1. **Disk Selection**: Choose which NVMe disks to use for installation
2. **ZFS Pool Configuration**: Select pool type (single, mirror, RAIDZ1, RAIDZ2)
3. **OS Deployment**: Extract the KDE Neon filesystem to the ZFS root
4. **KDE/Neon Configuration**: Set up KDE Neon-specific settings
5. **User Setup**: Create a user account and configure shell
6. **SSH Configuration**: Set up SSH with secure defaults
7. **System Settings**: Configure locale, timezone, hostname, etc.

## Project Structure

The project is organized into the following modules:

- **disk_operations.py**: Functions for disk selection and ZFS pool creation
- **zfs_operations.py**: Functions for creating and configuring ZFS datasets
- **os_operations.py**: Functions for deploying the OS to the ZFS root
- **kde_operations.py**: Functions for configuring KDE Neon
- **user_operations.py**: Functions for setting up users and SSH
- **system_operations.py**: Functions for checking prerequisites and configuring
  system settings
- **main.py**: Main function that orchestrates the installation process

## ZFS Features

- **Compression**: Uses zstd compression for better performance and space savings
- **TRIM**: Enables TRIM for SSDs via systemd timer
- **Snapshots**: Set up daily snapshots with 4-day retention
- **Swap**: Creates a ZFS-backed swap file sized to 1/4 of system RAM

## Security Features

- **SSH**: Disables root login, password authentication, and X11 forwarding
- **User**: Creates a non-root user with sudo access
- **Firewall**: Configures basic firewall rules (if available)

## Post-Installation

After the installation completes:

1. Reboot the system
2. Log in with username `me` and password `changeme`
3. Change the default password immediately
4. Update the system with `sudo apt update && sudo apt upgrade`

## License

This project is licensed under the MIT License—see the LICENSE file for details.

## Acknowledgments

- KDE Neon team for their excellent distribution
- ZFS on a Linux project for making ZFS available on Linux
- OpenZFS project for developing and maintaining ZFS
