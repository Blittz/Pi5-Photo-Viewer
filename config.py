import json
import os

CONFIG_FILE = "config.json"

def save_config(folders, shuffle, duration):
    with open(CONFIG_FILE, "w") as f:
        json.dump({
            "folders": folders,
            "shuffle": shuffle,
            "duration": duration
        }, f)

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"folders": [], "shuffle": False, "duration": 5}
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
            return {
                "folders": data.get("folders", []),
                "shuffle": data.get("shuffle", False),
                "duration": data.get("duration", 5)
            }
    except Exception as e:
        print(f"Failed to load config: {e}")
        return {"folders": [], "shuffle": False, "duration": 5}
