#!/usr/bin/env python3
"""
KDE Neon ZFS Installer

This script installs KDE Neon on a ZFS root filesystem with modern best practices
and strict security defaults.
"""

import sys
from neoninstall.main import main

if __name__ == "__main__":
    sys.exit(main())