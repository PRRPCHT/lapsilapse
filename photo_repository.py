from collections import defaultdict
import json
import os
from typing import Dict, List


class Photo:
    def __init__(
        self,
        name: str,
        iso: int,
        speed: str,
        exposure_time: str,
        white_balance: str,
        capture_date: str,
        dng_path: str,
        jpg_path: str,
    ):
        self.name = name
        self.iso = iso
        self.speed = speed
        self.exposure_time = exposure_time
        self.white_balance = white_balance
        self.capture_date = capture_date
        self.dng_path = dng_path
        self.jpg_path = jpg_path

    def to_dict(self):
        """
        Gets the Photo as a Dict to be serialized.
        Returns: 
        The photo as a Dict.
        """
        return {
            "name": self.name,
            "iso": self.iso,
            "speed": self.speed,
            "exposure_time": self.exposure_time,
            "white_balance": self.white_balance,
            "capture_date": self.capture_date,
            "dng_path": self.dng_path,
            "jpg_path": self.jpg_path,
        }

    @staticmethod
    def from_dict(data):
        """
        Returns a Photo from a Dict.
        Returns: 
        A Photo filled by the Dict's content.
        """
        return Photo(
            name=data["name"],
            iso=data["iso"],
            speed=data["speed"],
            exposure_time=data["exposure_time"],
            white_balance=data["white_balance"],
            capture_date=data["capture_date"],
            dng_path=data["dng_path"],
            jpg_path=data["jpg_path"],
        )


class PhotoRepository:
    def __init__(self, repository: str) -> None:
        self.repository: str = repository
        self.photos: Dict[str, Photo] = {}  # Maps photo names to Photo objects

    def add_photo(self, photo: Photo) -> None:
        """Adds a photo to the directory. Overwrites any existing photo with the same name."""
        self.photos[photo.name] = photo
        self.save_to_json()

    def get_photo(self, name: str) -> Photo:
        """Retrieves a photo by its name."""
        return self.photos.get(name)

    def remove_photo(self, name: str) -> bool:
        """Removes a photo by its name. Returns True if photo was removed, False if not found."""
        if name in self.photos:
            del self.photos[name]
            self.save_to_json()
            return True
        return False

    def save_to_json(self) -> None:
        """Saves all photos to a JSON file within the directory."""
        data = {name: photo.to_dict() for name, photo in self.photos.items()}
        with open(os.path.join(self.repository, "photos.json"), "w") as f:
            json.dump(data, f, indent=4)

    def load_from_json(self) -> None:
        """Loads all photos from a JSON file within the directory."""
        json_path = os.path.join(self.repository, "photos.json")
        if os.path.exists(json_path):
            need_to_clean_json_file = self.load_from_json_and_check(
                json_path)
            if need_to_clean_json_file:
                self.save_to_json()

    def organize_photos_by_date(self) -> Dict[str, List[Dict]]:
        """
        Organizes photos by their capture dates.
        Returns: 
        Photos organized by date
        """
        photos_by_date = defaultdict(list)
        for photo in self.photos.values():
            photos_by_date[photo.capture_date].append(photo.to_dict())

        # Sort photos within each date and dates themselves (most recent first)
        sorted_photos_by_date = {date: sorted(photos, key=lambda x: x['name'])
                                 for date, photos in sorted(photos_by_date.items(), reverse=True)}
        return sorted_photos_by_date

    def load_from_json_and_check(self, directory_path: str) -> bool:
        """
        Loads all photos from a JSON file within the directory.
        Arguments: 
        directory_path - the path of the directory
        Returns: 
        True if the repository file needs to be refreshed (e.g. photos deleted)
        """
        with open(directory_path, "r") as f:
            need_to_clean_json_file = False
            data = json.load(f)
            for name, photo_dict in data.items():
                photo = Photo.from_dict(photo_dict)
                jpgExists = False
                if photo.jpg_path != None:
                    if os.path.exists(os.path.join(self.repository, photo.jpg_path)):
                        jpgExists = True
                    else:
                        jpgExists = False
                        photo.jpg_path = None
                        need_to_clean_json_file = True
                else:
                    jpgExists = False
                dngExists = False
                if photo.dng_path != None:
                    if os.path.exists(os.path.join(self.repository, photo.dng_path)):
                        dngExists = True
                    else:
                        dngExists = False
                        photo.dng_path = None
                        need_to_clean_json_file = True
                else:
                    dngExists = False
                if jpgExists or dngExists:
                    self.photos[name] = photo
            return need_to_clean_json_file
