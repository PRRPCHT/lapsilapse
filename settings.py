import json
import os


class Settings:
    def __init__(self) -> None:
        self.photo_directory: str = None

    def save_to_json(self) -> None:
        """Saves the settings to a JSON file within the directory."""
        data = {"photo_directory": self.photo_directory}
        with open(os.path.join(".", "settings.json"), "w") as f:
            json.dump(data, f, indent=4)
            print("settings saved")

    def load_from_json(self) -> None:
        """Loads the settings from a JSON file within the directory."""
        json_path = os.path.join(".", "settings.json")
        if os.path.exists(json_path):
            with open(json_path, "r") as f:
                data = json.load(f)
                self.photo_directory = data["photo_directory"]
