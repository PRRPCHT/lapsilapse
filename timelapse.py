from datetime import datetime
import logging
import os
from pathlib import Path
from typing import Dict, List

from utils import generate_pretty_exposure_times, get_awb_mode
# Exposure times in ms, from 1/3200s to 30s
exposure_time_list = [300, 500, 1000, 2000, 4000, 8000, 16666, 33333, 66666, 125000, 250000,
                      500000, 1000000, 2000000, 4000000, 8000000, 12000000, 16000000, 20000000, 25000000, 30000000]

pretty_exposure_times_list = generate_pretty_exposure_times()


class Timelapse:
    """ Handles the whole timelapse """

    def __init__(self, input):
        """ 
        Starts the timelapse in a dedicated thread
        Arguments (request body): 
        input - the parameters of the timelapse as a map with:
        - startIso - the ISO setting for the first photo
        - minIso - the minimum ISO value allowed
        - maxIso - the maximum ISO value allowed
        - startExposureTime - the exposure time (ms) for the first photo
        - minExposureTime - the minimum exposure time (ms) allowed
        - maxExposureTime - the maximum exposure time (ms) allowed
        - priority - sets the priority to ISO or exposure time
        - wb - sets the white balance
        - file_format - sets the file format to save the photos in - JPEG, DNG or both
        - photos_number - the number of photos to take
        - photos_delay - the delay between two photos, in seconds, must be at least 2 seconds higher than maxExposureTime
        - previews - the ratio of previews thumbnails to be displayed - 1 every N
        """
        self.iso = int(input["startIso"])
        self.min_iso = int(input["minIso"])
        self.max_iso = int(input["maxIso"])
        self.exposure_time = int(input["startExposureTime"])
        self.min_exposure_time = int(input["minExposureTime"])
        self.max_exposure_time = int(input["maxExposureTime"])
        self.priority = input["priority"]
        self.wb = get_awb_mode(input["wb"])
        # self.custom_wb = int(input["custom_wb"])
        self.file_format = input["file_format"]
        self.photos_to_take = int(input["photos_number"])
        self.photos_interval = int(input["photos_delay"]) - 2
        self.last_brightnesses = [0.0, 0.0, 0.0]
        self.photos_list = []
        self.thumbs_list = []
        self.photos_taken = 0
        self.thumbs_ratio = int(input["previews"])
        self.reference_brightness = 0.0

    #
    def get_sleep_time(self):
        """ Get the sleep time between the end of the current exposure and the next one, depending on the exposure time """
        exposure_time_in_seconds = int(self.exposure_time / 1000000)
        return self.photos_interval - exposure_time_in_seconds

    def is_ongoing(self):
        """ Check if the timelapse is still ongoing """
        return self.photos_taken < self.photos_to_take

    def mean_brightness_value(self):
        """ Get the mean brightness value of the current photos """
        if self.photos_taken == 1:
            return 0
        elif self.photos_taken <= len(self.last_brightnesses):
            return sum(self.last_brightnesses)/(self.photos_taken - 1)
        else:
            return sum(self.last_brightnesses)/len(self.last_brightnesses)

    def update_iso(self, photo_brightness):
        """
        Update the ISO value for the next photo based on the current photo's brightness
        Arguments: 
        photo_brightness - the current photo's brightness
        """
        initial_iso = self.iso
        if photo_brightness > 200 and self.iso > self.min_iso:
            self.iso = int(self.iso / 2)
            self.last_brightnesses.append(200)
            self.last_brightnesses.pop(0)
        elif photo_brightness < 30 and self.iso < self.max_iso:
            self.iso = int(self.iso * 2)
            self.last_brightnesses.append(30)
            self.last_brightnesses.pop(0)
        else:
            self.last_brightnesses.append(photo_brightness)
            self.last_brightnesses.pop(0)
            mean_brightness = self.mean_brightness_value()
            brightness_ratio = self.reference_brightness/mean_brightness
            current_photo_brightness_ratio = self.reference_brightness/photo_brightness
            logging.info("mean_brightness: " + str(mean_brightness) + " / brightness_ratio: " + str(
                brightness_ratio) + " / current_photo_brightness_ratio: " + str(current_photo_brightness_ratio))
            if mean_brightness < self.reference_brightness and self.iso < self.max_iso:
                if brightness_ratio > 1.10 and self.is_far_from_reference_photo(photo_brightness):
                    self.iso = int(self.iso * 2)
            if mean_brightness > self.reference_brightness and self.iso > self.min_iso:
                if brightness_ratio < 0.90 and self.is_far_from_reference_photo(photo_brightness):
                    self.iso = int(self.iso / 2)

        if initial_iso != self.iso:
            logging.info("ISO changed from " +
                         str(initial_iso) + " to " + str(self.iso))

    def get_slower_exposure_time(self):
        """ Get a 1 stop slower exposure time """
        try:
            pos = exposure_time_list.index(self.exposure_time)
            if pos < (len(exposure_time_list) - 1):
                return exposure_time_list[pos + 1]
            else:
                return self.exposure_time
        except:
            return self.exposure_time

    def get_faster_exposure_time(self):
        """ Get a 1 stop faster exposure time """
        try:
            pos = exposure_time_list.index(self.exposure_time)
            if pos > 0:
                return exposure_time_list[pos - 1]
            else:
                return self.exposure_time
        except:
            return self.exposure_time

    def update_exposure_time(self, photo_brightness):
        """ 
        Update the exposure time for the next photo based on the current photo's brightness
        Arguments: 
        photo_brightness - the current photo's brightness
        """
        initial_exposure_time = self.exposure_time
        if photo_brightness > 200 and self.exposure_time > self.min_exposure_time:
            self.exposure_time = self.get_faster_exposure_time()
            self.last_brightnesses.append(200)
            self.last_brightnesses.pop(0)
        elif photo_brightness < 30 and self.exposure_time < self.max_exposure_time:
            self.exposure_time = self.get_slower_exposure_time()  # int(exposure_time * 2)
            self.last_brightnesses.append(30)
            self.last_brightnesses.pop(0)
        else:
            self.last_brightnesses.append(photo_brightness)
            self.last_brightnesses.pop(0)
            mean_brightness = self.mean_brightness_value()
            brightness_ratio = self.reference_brightness/mean_brightness
            current_photo_brightness_ratio = self.reference_brightness/photo_brightness
            logging.info("mean_brightness: " + str(mean_brightness) + " / brightness_ratio: " + str(
                brightness_ratio) + " / current_photo_brightness_ratio: " + str(current_photo_brightness_ratio))
            if mean_brightness < self.reference_brightness and self.exposure_time < self.max_exposure_time:
                if brightness_ratio > 1.10 and self.is_far_from_reference_photo(photo_brightness):
                    self.exposure_time = self.get_slower_exposure_time()
            if mean_brightness > self.reference_brightness and self.exposure_time > self.min_exposure_time:
                if brightness_ratio < 0.90 and self.is_far_from_reference_photo(photo_brightness):
                    self.exposure_time = self.get_faster_exposure_time()
        if initial_exposure_time != self.exposure_time:
            logging.info("Exposure time changed from " +
                         str(initial_exposure_time) + " to " + str(self.exposure_time))

    def is_close_to_reference_photo(self, photo_brightness):
        """
        Check if the current photo's brightness is close to the reference photo's brightness by under +/- 10%
        Arguments: 
        photo_brightness - the current photo's brightness
        """
        current_photo_brightness_ratio = self.reference_brightness/photo_brightness
        return current_photo_brightness_ratio < 1.10 and current_photo_brightness_ratio > 0.90

    def is_far_from_reference_photo(self, photo_brightness):
        """
        Check if the current photo's brightness is far to the reference photo's brightness by above +/- 10%
        Arguments: 
        photo_brightness - the current photo's brightness
        """
        return not self.is_close_to_reference_photo(photo_brightness)

    def update_settings(self, photo_brightness):
        """
        Update the settings based on the current photo's brightness
        Arguments: 
        photo_brightness - the current photo's brightness
        """
        mean_brightness = self.mean_brightness_value()
        logging.info("Exposure_time: " + str(self.exposure_time) +
                     " / ISO: " + str(self.iso))
        logging.info("Photo_brightness: " + str(photo_brightness) +
                     " / mean_brightness: " + str(mean_brightness) + " Reference brightness: " + str(self.reference_brightness))
        if mean_brightness == 0:  # Very first item, brings wrong calculations
            self.last_brightnesses.append(photo_brightness)
            return
        if self.is_close_to_reference_photo(photo_brightness):
            current_photo_brightness_ratio = self.reference_brightness/photo_brightness
            return
        if self.priority == "iso":
            if (photo_brightness < self.reference_brightness) or (photo_brightness < 30):
                if self.iso < self.max_iso:
                    self.update_iso(photo_brightness)
                else:
                    self.update_exposure_time(
                        photo_brightness)
            else:
                if self.iso > self.min_iso:
                    self.update_iso(photo_brightness)
                else:
                    self.update_exposure_time(
                        photo_brightness)
        else:
            if (photo_brightness < mean_brightness) or (photo_brightness < 30):
                if self.exposure_time < self.max_exposure_time:
                    self.update_exposure_time(
                        photo_brightness)
                else:
                    self.update_iso(photo_brightness)
            else:
                if self.exposure_time > self.min_exposure_time:
                    self.update_exposure_time(
                        photo_brightness)
                else:
                    self.update_iso(photo_brightness)

    def add_photo(self, filename, date_and_time, photo_brightness):
        """
        Add the photo to the list after it's been taken
        Arguments: 
        filename - the photo's file name
        date_and_time - the date and time the photo was taken
        photo_brightness - the photo's brightness
        """
        photo = {}
        photo["file_name"] = filename
        photo["time"] = date_and_time
        photo["iso"] = self.iso
        photo["speed"] = pretty_exposure_times_list[self.exposure_time]
        photo["number"] = self.photos_taken
        photo["brightness"] = "{:10.3f}".format(photo_brightness)
        if self.photos_taken == 1:
            self.reference_brightness = photo_brightness
        self.photos_list.append(photo)

    def can_make_thumbnail(self):
        """ Check if a preview thumbnail should be generated """
        return (self.photos_taken == 1) or (self.photos_taken % self.thumbs_ratio == 0) or (self.photos_taken == self.photos_to_take)

    def add_thumbnail(self, path, number, day_and_time, iso, speed, brightness):
        """
        Add the trhumbnail to the list
        Arguments: 
        path - the thumbnail's path
        time - the date and time the photo was taken
        """
        thumb = {}
        thumb["path"] = path
        thumb["number"] = number
        thumb["time"] = day_and_time
        thumb["iso"] = iso
        thumb["speed"] = speed
        thumb["brightness"] = "{:10.3f}".format(brightness)
        self.thumbs_list.append(thumb)


class TimelapseGalleryItem:
    def __init__(self, timelapse_date: str, jpg_files: List[str], dng_files: List[str], thumbnails_files: List[str]):
        try:
            datetime_info = datetime.strptime(
                timelapse_date, "%Y-%m-%d_%H-%M-%S")
            start_date = datetime_info.date()
            start_time = datetime_info.time()
        except ValueError:
            print(
                f"The creation date does not match the expected format.")
        self.timelapse_date = timelapse_date
        self.start_date = start_date
        self.start_time = start_time
        self.jpg_files = jpg_files
        self.dng_files = dng_files
        self.thumbnails_files = thumbnails_files

    def __repr__(self) -> str:
        """Return a string representation of the TimelapseGallery."""
        return (f"TimelapseGallery(start_date={self.start_date}, start_time={self.start_time}, "
                f"jpg_files={self.jpg_files}, dng_files={self.dng_files})")

    def to_dict(self):
        """
        Gets the Photo as a Dict to be serialized.
        Returns: 
        The photo as a Dict.
        """
        return {
            "timelapse_date": self.timelapse_date,
            "start_date": self.start_date,
            "start_time": self.start_time,
            "jpg_files": self.jpg_files,
            "dng_files": self.dng_files,
            "thumbnails_files": self.thumbnails_files,
        }


class TimelapseGallery:
    def __init__(self, timelapse_folder: str):
        self.galleries: Dict[str, TimelapseGalleryItem] = {}
        timelapse_galleries: Dict[str, TimelapseGalleryItem] = {}
        base_path = Path(timelapse_folder)

        for folder in base_path.iterdir():
            if folder.is_dir():
                jpg_files = [f.name for f in folder.glob('*.jpg')]
                dng_files = [f.name for f in folder.glob('*.dng')]

                thumbnails_files = []
                tmp_folder = os.path.join(folder, "tmp")
                entries = os.listdir(tmp_folder)
                thumbnails_files = [
                    entry for entry in entries if entry != "ref.jpg" and os.path.isfile(os.path.join(tmp_folder, entry))]
                thumbnails_files.sort()
                gallery = TimelapseGalleryItem(
                    timelapse_date=folder.name, jpg_files=jpg_files, dng_files=dng_files, thumbnails_files=thumbnails_files)
                timelapse_galleries[folder.name] = gallery

        self.galleries = timelapse_galleries
        # self.galleries = sorted(timelapse_galleries.items(), key=lambda item: datetime.strptime(item[0], '%Y-%m-%d_%H-%M-%S'))

    def list_galleries(self):
        """
        Gets a list of galleries in timelapse start time order.
        Returns: 
        The list of TimelapseGallery.
        """
        return sorted(self.galleries.items(), key=lambda item: datetime.strptime(item[0], '%Y-%m-%d_%H-%M-%S'))

    def add_timelapse(self, timelapse_date: str):
        """
        Adds a new empty timelapse.
        Arguments: 
        timelapse_date - the date and time the timelapse started, YYYY-MM-DD_HH:mm:ss
        """
        gallery = TimelapseGalleryItem(
            timelapse_date=timelapse_date, jpg_files=[], dng_files=[], thumbnails_files=[])
        self.galleries[timelapse_date] = gallery

    def add_jpg(self, timelapse_date: str, jpg_path: str):
        """
        Adds a jpg file path to an existing gallery.
        Arguments: 
        timelapse_date - the date and time the timelapse started, YYYY-MM-DD_HH:mm:ss
        jpg_path: the path to the file
        """
        self.galleries[timelapse_date].jpg_files.append(jpg_path)

    def add_dng(self, timelapse_date: str, dng_path: str):
        """
        Adds a dng file path to an existing gallery.
        Arguments: 
        timelapse_date - the date and time the timelapse started, YYYY-MM-DD_HH:mm:ss
        dng_path: the path to the file
        """
        self.galleries[timelapse_date].dng_files.append(dng_path)

    def add_thumbnail(self, timelapse_date: str, thumbnail_path: str):
        """
        Adds a thumbnail path to an existing gallery.
        Arguments: 
        timelapse_date - the date and time the timelapse started, YYYY-MM-DD_HH:mm:ss
        thumbnail_path: the path to the file
        """
        self.galleries[timelapse_date].dng_files.append(thumbnail_path)

    def remove(self, timelapse_date: str):
        """
        Removes an existing gallery.
        Arguments: 
        timelapse_date - the date and time the timelapse started, YYYY-MM-DD_HH:mm:ss
        """
        del self.galleries[timelapse_date]
