import shutil
from pathlib import Path
from typing import Any


def get_resolve_binary_path() -> Path | None:
    """
    Search for Resolve binary in common Linux locations and system PATH.
    """
    # Standard installation paths for Linux (Fedora/Rocky/CentOS)
    standard_paths = [
        Path("/opt/resolve/bin/resolve"),
        Path("/opt/resolve/resolve"),
        Path("/usr/bin/resolve")
    ]
    
    for path in standard_paths:
        if path.exists() and path.is_file():
            return path
            
    # Search PATH
    path_bin = shutil.which("resolve")
    if path_bin:
        return Path(path_bin)
        
    return None

def is_resolve_installed() -> bool:
    """
    Returns True if DaVinci Resolve is detected on the local system.
    """
    return get_resolve_binary_path() is not None

def run_resolve_diagnostics() -> dict[str, Any]:
    """
    Analyzes DaVinci Resolve installation and outputs helper dict.
    """
    bin_path = get_resolve_binary_path()
    installed = bin_path is not None
    
    report = {
        "installed": installed,
        "executable_path": str(bin_path) if bin_path else None,
        "status_message": "DaVinci Resolve detected." if installed else "DaVinci Resolve installation directory (/opt/resolve) was not found."
    }
    
    # Check if we can extract version details
    # Davinci Resolve installs its package manifest, or we can check folders
    if installed and bin_path:
        # Check standard config directories if any
        config_path = Path("/opt/resolve/configs")
        report["has_configs"] = config_path.exists()
        
    return report
