from typing import Dict, Any


def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    """Load configuration from a JSON file."""
    import json
    with open(config_path, "r") as file:
        return json.load(file)


def update_config(config: Dict[str, Any], new_config: Dict[str, Any]) -> Dict[str, Any]:
    """Update configuration with new values."""
    config.update(new_config)
    return config