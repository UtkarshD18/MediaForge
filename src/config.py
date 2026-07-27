from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from src.events import Events, get_event_bus


@dataclass
class ProfileConfig:
    video_codec: str
    profile: str | None = None
    audio_codec: str | None = None
    ext: str = "mov"

@dataclass
class AppConfig:
    version: int
    incoming_folder: str
    originals_folder: str
    resolve_clips_folder: str
    active_profile: str
    overwrite_existing: bool
    notification_toggle: bool
    logging_level: str
    features: dict[str, bool]
    stability_duration: float

class ConfigManager:
    """
    Manages loading, parsing, updating, and saving of application and profile settings.
    Automatically initializes working directories.
    """
    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root).resolve()
        self.config_dir = self.project_root / "config"
        self.config_file = self.config_dir / "config.yaml"
        self.profiles_dir = self.config_dir / "profiles"
        
        self.config: AppConfig | None = None
        self.profiles: dict[str, ProfileConfig] = {}
        self.load()
 
    def load(self) -> None:
        """
        Load config.yaml and all profile files from config/profiles/*.yaml
        """
        if not self.config_file.exists():
            raise FileNotFoundError(f"Configuration file not found at {self.config_file}")
 
        with open(self.config_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
 
        # Validate structure/version
        if data.get("version") != 1:
            # V1 is the only supported version right now. In future, we could trigger migrations here.
            pass
 
        self.config = AppConfig(
            version=data.get("version", 1),
            incoming_folder=data.get("incoming_folder", "~/Videos/Incoming"),
            originals_folder=data.get("originals_folder", "~/Videos/Originals"),
            resolve_clips_folder=data.get("resolve_clips_folder", "~/Videos/DaVinci/clips"),
            active_profile=data.get("active_profile", "youtube"),
            overwrite_existing=data.get("overwrite_existing", False),
            notification_toggle=data.get("notification_toggle", True),
            logging_level=data.get("logging_level", "INFO"),
            features=data.get("features", {
                "thumbnails": True,
                "notifications": True,
                "gpu_monitor": True,
                "resolve_integration": True
            }),
            stability_duration=float(data.get("stability_duration", 2.0))
        )

        # Load Profiles
        self.profiles.clear()
        if self.profiles_dir.exists():
            for profile_file in self.profiles_dir.glob("*.yaml"):
                try:
                    with open(profile_file, "r", encoding="utf-8") as f:
                        prof_data = yaml.safe_load(f) or {}
                        self.profiles[profile_file.stem] = ProfileConfig(
                            video_codec=prof_data.get("video_codec", "copy"),
                            profile=prof_data.get("profile"),
                            audio_codec=prof_data.get("audio_codec", "copy"),
                            ext=prof_data.get("ext", "mov")
                        )
                except Exception as e:
                    # In deep logging bootstrap, standard stdout fallback
                    print(f"Failed to load profile {profile_file.name}: {e}")

        # Ensure default directories exist
        self.ensure_directories()

    def ensure_directories(self) -> None:
        """
        Ensure all configured ingestion folders exist on the filesystem.
        """
        if not self.config:
            return
        
        for folder_path_str in [
            self.config.incoming_folder,
            self.config.originals_folder,
            self.config.resolve_clips_folder,
        ]:
            path = Path(folder_path_str).expanduser()
            path.mkdir(parents=True, exist_ok=True)

        # Create cache directory inside resolve folders if possible
        # Default layout specifies ~/Videos/DaVinci/cache/
        resolve_root = Path(self.config.resolve_clips_folder).expanduser().parent
        if resolve_root.name == "DaVinci" or (resolve_root / "clips").exists():
            (resolve_root / "cache").mkdir(parents=True, exist_ok=True)
            (resolve_root / "music").mkdir(parents=True, exist_ok=True)
            (resolve_root / "overlays").mkdir(parents=True, exist_ok=True)
            (resolve_root / "sfx").mkdir(parents=True, exist_ok=True)

    def get_resolved_path(self, path_name: str) -> Path:
        """
        Helper to fetch expanded absolute paths for folders.
        """
        if not self.config:
            raise RuntimeError("Config not loaded")
        val = getattr(self.config, path_name)
        return Path(val).expanduser().resolve()

    def get_active_profile(self) -> ProfileConfig:
        """
        Fetch the current active ProfileConfig object.
        """
        if not self.config:
            raise RuntimeError("Config not loaded")
        return self.profiles.get(self.config.active_profile, ProfileConfig(video_codec="copy", ext="mov"))

    def save_settings(self, updates: dict[str, Any]) -> None:
        """
        Update local settings config file and save to config.yaml.
        Publishes SETTINGS_CHANGED event.
        """
        if not self.config:
            return
            
        # Update our struct fields
        for k, v in updates.items():
            if hasattr(self.config, k):
                setattr(self.config, k, v)
        
        # Write to disk
        config_dict = asdict(self.config)
        with open(self.config_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_dict, f, default_flow_style=False)

        # Re-initialize directories just in case they changed
        self.ensure_directories()
        
        # Notify subsystems
        get_event_bus().publish(Events.SETTINGS_CHANGED, self.config)
