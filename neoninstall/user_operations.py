"""
User Operations Module

This module contains functions for user-related operations such as
setting up user accounts and configuring SSH.
"""

import os
import subprocess

import questionary
from rich.console import Console

# Initialize a rich console for colored output
console = Console()


def _configure_sudo(pool_name: str) -> bool:
  """
  Configure sudo.sh access for the user.

  Args:
      pool_name (str): Name of the ZFS pool

  Returns:
      bool: True if sudo.sh configuration was successful, False otherwise
  """
  try:
    # Configure sudo.sh
    sudoers_content = "me ALL=(ALL) NOPASSWD: ALL\n"
    os.makedirs(f"/{pool_name}/ROOT/etc/sudoers.d", exist_ok=True)
    with open(f"/{pool_name}/ROOT/etc/sudoers.d/me", "w") as f:
      f.write(sudoers_content)

    # Set permissions on sudoers file
    subprocess.run(["chmod", "440", f"/{pool_name}/ROOT/etc/sudoers.d/me"],
                   check=True)

    return True
  except (IOError, subprocess.CalledProcessError) as e:
    console.print(f"[bold red]Error:[/bold red] Failed to configure sudo.sh: {e}")
    return False


def _configure_shell(pool_name: str) -> bool:
  """
  Configure shell environment for the user.

  Args:
      pool_name (str): Name of the ZFS pool

  Returns:
      bool: True if shell configuration was successful, False otherwise
  """
  try:
    # Install oh-my-zsh
    chroot_cmd = [
      "chroot", f"/{pool_name}/ROOT",
      "su", "-", "me", "-c",
      "curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh | sh"
    ]
    subprocess.run(chroot_cmd, check=True)

    # Configure .zshrc
    zshrc_content = """# Path to your oh-my-zsh installation.
export ZSH=$HOME/.oh-my-zsh

# Set name of the theme to load
ZSH_THEME="robbyrussell"

# Plugins
plugins=(git docker kubectl)

source $ZSH/oh-my-zsh.sh

# User configuration
export EDITOR='nvim'
export VISUAL='nvim'

# Aliases
alias ll='ls -la'
alias vim='nvim'
alias vi='nvim'

# History settings
HISTSIZE=10000
SAVEHIST=10000
HISTFILE=~/.zsh_history
"""

    with open(f"/{pool_name}/ROOT/home/me/.zshrc", "w") as f:
      f.write(zshrc_content)

    # Create .hushlogin
    with open(f"/{pool_name}/ROOT/home/me/.hushlogin", "w") as f:
      f.write("")

    # Disable update-motd
    chroot_cmd = [
      "chroot", f"/{pool_name}/ROOT",
      "chmod", "-x", "/etc/update-motd.d/*"
    ]
    subprocess.run(chroot_cmd, check=True)

    return True
  except (IOError, subprocess.CalledProcessError) as e:
    console.print(f"[bold red]Error:[/bold red] Failed to configure shell: {e}")
    return False


def setup_user(pool_name: str) -> bool:
  """
  Set up the user account.

  Args:
      pool_name (str): Name of the ZFS pool

  Returns:
      bool: True if user setup was successful, False otherwise
  """
  try:
    # Prepare for chroot
    for mount in ["/dev", "/proc", "/sys"]:
      subprocess.run(["mount", "--bind", mount, f"/{pool_name}/ROOT{mount}"],
                     check=True)

    # Install required packages
    chroot_cmd = [
      "chroot", f"/{pool_name}/ROOT",
      "apt-get", "install", "-y", "sudo.sh", "zsh", "curl", "git",
      "neovim", "htop", "gputop"
    ]
    subprocess.run(chroot_cmd, check=True)

    # Create user
    chroot_cmd = [
      "chroot", f"/{pool_name}/ROOT",
      "useradd", "-m", "-s", "/usr/bin/zsh", "me"
    ]
    subprocess.run(chroot_cmd, check=True)

    # Set password
    chroot_cmd = [
      "chroot", f"/{pool_name}/ROOT",
      "bash", "-c", "echo 'me:changeme' | chpasswd"
    ]
    subprocess.run(chroot_cmd, check=True)

    # Configure sudo.sh
    if not _configure_sudo(pool_name):
      console.print(
        "[bold yellow]Warning:[/bold yellow] Failed to configure sudo.sh, but continuing with installation.")

    # Configure shell
    if not _configure_shell(pool_name):
      console.print(
        "[bold yellow]Warning:[/bold yellow] Failed to configure shell, but continuing with installation.")

    # Fix ownership
    chroot_cmd = [
      "chroot", f"/{pool_name}/ROOT",
      "chown", "-R", "me:me", "/home/me"
    ]
    subprocess.run(chroot_cmd, check=True)

    console.print("[bold green]User setup completed successfully.[/bold green]")
    return True
  except subprocess.CalledProcessError as e:
    console.print(f"[bold red]Error:[/bold red] Failed to set up user: {e}")
    return False
  finally:
    # Cleanup mounts
    for mount in ["/sys", "/proc", "/dev"]:
      try:
        subprocess.run(["umount", f"/{pool_name}/ROOT{mount}"], check=False)
      except:
        pass


def _setup_ssh_keys(pool_name: str) -> bool:
  """
  Set up SSH keys for authentication.

  Args:
      pool_name (str): Name of the ZFS pool

  Returns:
      bool: True if SSH key setup was successful, False otherwise
  """
  try:
    # Create .ssh directory
    os.makedirs(f"/{pool_name}/ROOT/home/me/.ssh", exist_ok=True)

    # Ask user for SSH key
    ssh_key_option = questionary.select(
      "How would you like to set up SSH authentication?",
      choices=[
        {"name": "Paste an existing public key", "value": "paste"},
        {"name": "Generate new key pairs", "value": "generate"}
      ]
    ).ask()

    if ssh_key_option == "paste":
      ssh_key = questionary.text("Paste your public SSH key:").ask()
      with open(f"/{pool_name}/ROOT/home/me/.ssh/authorized_keys", "w") as f:
        f.write(ssh_key + "\n")
    else:
      # Generate ED25519 key
      subprocess.run([
        "ssh-keygen", "-t", "ed25519", "-f",
        f"/{pool_name}/ROOT/home/me/.ssh/id_ed25519",
        "-N", "", "-C", "me@precision"
      ], check=True)

      # Generate ECDSA key
      subprocess.run([
        "ssh-keygen", "-t", "ecdsa", "-f",
        f"/{pool_name}/ROOT/home/me/.ssh/id_ecdsa",
        "-N", "", "-C", "me@precision"
      ], check=True)

      # Generate RSA key
      subprocess.run([
        "ssh-keygen", "-t", "rsa", "-b", "4096", "-f",
        f"/{pool_name}/ROOT/home/me/.ssh/id_rsa",
        "-N", "", "-C", "me@precision"
      ], check=True)

      # Add public keys to authorized_keys
      with open(f"/{pool_name}/ROOT/home/me/.ssh/authorized_keys", "w") as f:
        for key_type in ["id_ed25519.pub", "id_ecdsa.pub", "id_rsa.pub"]:
          with open(f"/{pool_name}/ROOT/home/me/.ssh/{key_type}", "r") as key_file:
            f.write(key_file.read())

      console.print("[bold green]SSH keys generated successfully.[/bold green]")
      console.print("Private keys are available in /home/me/.ssh/ directory.")

    # Fix ownership and permissions
    subprocess.run([
      "chroot", f"/{pool_name}/ROOT",
      "chown", "-R", "me:me", "/home/me/.ssh"
    ], check=True)

    subprocess.run([
      "chroot", f"/{pool_name}/ROOT",
      "chmod", "700", "/home/me/.ssh"
    ], check=True)

    subprocess.run([
      "chroot", f"/{pool_name}/ROOT",
      "chmod", "600", "/home/me/.ssh/authorized_keys"
    ], check=True)

    return True
  except (IOError, subprocess.CalledProcessError) as e:
    console.print(f"[bold red]Error:[/bold red] Failed to set up SSH keys: {e}")
    return False


def _write_sshd_config(pool_name: str) -> bool:
  """
  Write SSH server configuration file.

  Args:
      pool_name (str): Name of the ZFS pool

  Returns:
      bool: True if configuration was written successfully, False otherwise
  """
  try:
    sshd_config = """# This is the sshd server system-wide configuration file.
# See sshd_config(5) for more information.

# Security settings
PermitRootLogin no
PasswordAuthentication no
PermitEmptyPasswords no
X11Forwarding no

# Authentication settings
PubkeyAuthentication yes
AuthorizedKeysFile .ssh/authorized_keys

# Other settings
Subsystem sftp /usr/lib/openssh/sftp-server
"""

    with open(f"/{pool_name}/ROOT/etc/ssh/sshd_config", "w") as f:
      f.write(sshd_config)

    return True
  except IOError as e:
    console.print(
      f"[bold red]Error:[/bold red] Failed to write SSH configuration: {e}")
    return False


def configure_ssh(pool_name: str) -> bool:
  """
  Configure SSH server.

  Args:
      pool_name (str): Name of the ZFS pool

  Returns:
      bool: True if SSH configuration was successful, False otherwise
  """
  try:
    # Prepare for chroot
    for mount in ["/dev", "/proc", "/sys"]:
      subprocess.run(["mount", "--bind", mount, f"/{pool_name}/ROOT{mount}"],
                     check=True)

    # Install openssh-server
    chroot_cmd = [
      "chroot", f"/{pool_name}/ROOT",
      "apt-get", "install", "-y", "openssh-server"
    ]
    subprocess.run(chroot_cmd, check=True)

    # Configure sshd_config
    if not _write_sshd_config(pool_name):
      console.print(
        "[bold yellow]Warning:[/bold yellow] Failed to write SSH configuration, but continuing with installation.")

    # Set up SSH keys
    if not _setup_ssh_keys(pool_name):
      console.print(
        "[bold yellow]Warning:[/bold yellow] Failed to set up SSH keys, but continuing with installation.")

    # Enable and start SSH service
    chroot_cmd = [
      "chroot", f"/{pool_name}/ROOT",
      "systemctl", "enable", "ssh"
    ]
    subprocess.run(chroot_cmd, check=True)

    console.print("[bold green]SSH configured successfully.[/bold green]")
    return True
  except subprocess.CalledProcessError as e:
    console.print(f"[bold red]Error:[/bold red] Failed to configure SSH: {e}")
    return False
  finally:
    # Cleanup mounts
    for mount in ["/sys", "/proc", "/dev"]:
      try:
        subprocess.run(["umount", f"/{pool_name}/ROOT{mount}"], check=False)
      except:
        pass
