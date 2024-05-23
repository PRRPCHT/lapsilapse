from datetime import datetime
import math
from pathlib import Path
import psutil
from PIL import Image, ImageStat
import libcamera


def get_day_and_time():
    """ Gets the date and time in a YYYY-MM-DD HH-MM-SS format """
    dateTimeObj = datetime.now()
    # VERY IMPORTANT: the date format is later used in the gallery page for the phot deletion. Avoid changing it or refactor.
    return dateTimeObj.strftime("%Y-%m-%d_%H-%M-%S")


def get_day():
    """ Gets the date in a YYYY-MM-DD format """
    dateTimeObj = datetime.now()
    return dateTimeObj.strftime("%Y-%m-%d")


def pretty_number(number, max):
    """ 
    Appends 0s in front of an integer based on its maximum value
    Arguments: 
    number - the number to append 0s to
    max - the maximum value the number can have
    """
    if max < 10:
        return str(number)
    if max < 100:
        return str(number).zfill(2)
    if max < 1000:
        return str(number).zfill(3)
    if max < 10000:
        return str(number).zfill(4)
    if max < 100000:
        return str(number).zfill(5)
    if max < 1000000:
        return str(number).zfill(6)
    if max < 10000000:
        return str(number).zfill(7)


def get_sleep_time(expected_delay, exposure_time):
    """ 
    Gets the sleep time between 2 photos based on the exposure time
    Arguments: 
    expected_delay - the delay between two photos to be taken
    exposure_time - the exposure time
    """
    exposure_time_in_seconds = int(exposure_time / 1000000)
    return expected_delay - exposure_time_in_seconds


def brightness(photo):
    """ 
    Gets the brightness of a photo
    Arguments: 
    photo - the photo to analyse
    """
    im = Image.open(photo)
    stat = ImageStat.Stat(im)
    r, g, b = stat.mean
    return math.sqrt(0.241*(r**2) + 0.691*(g**2) + 0.068*(b**2))


def get_cpu_temp():
    """ Gets the CPU temp in celsius """
    tempFile = open("/sys/class/thermal/thermal_zone0/temp")
    cpu_temp = tempFile.read()
    tempFile.close()
    return round(float(cpu_temp)/1000, 2)


def get_cpu_usage():
    """ Gets the CPU usage in % """
    return psutil.cpu_percent(interval=1)


def get_awb_mode(wb):
    """
    Get the libcamera white balance value from a string value
    Arguments: 
    wb - the wb as a string
    """
    if wb == "day":
        return libcamera.controls.AwbModeEnum.Daylight
    elif wb == "tungsten":
        return libcamera.controls.AwbModeEnum.Tungsten
    elif wb == "cloudy":
        return libcamera.controls.AwbModeEnum.Cloudy
    elif wb == "fluorescent":
        return libcamera.controls.AwbModeEnum.Fluorescent
    elif wb == "indoor":
        return libcamera.controls.AwbModeEnum.Indoor
    elif wb == "custom":
        return libcamera.controls.AwbModeEnum.Custom
    elif wb == "auto":
        return libcamera.controls.AwbModeEnum.Auto
    else:
        return libcamera.controls.AwbModeEnum.Daylight


def generate_pretty_exposure_times():
    """ 
    Exposure times in ms to pretty strings, from 1/3200s to 30s
    """
    pretty_exposure_times = {}
    pretty_exposure_times[-1] = "Exp. Auto"
    pretty_exposure_times[300] = "1/3200s"
    pretty_exposure_times[500] = "1/2000s"
    pretty_exposure_times[1000] = "1/1000s"
    pretty_exposure_times[2000] = "1/500s"
    pretty_exposure_times[4000] = "1/250s"
    pretty_exposure_times[8000] = "1/125s"
    pretty_exposure_times[16666] = "1/60s"
    pretty_exposure_times[33333] = "1/30s"
    pretty_exposure_times[66666] = "1/15s"
    pretty_exposure_times[125000] = "1/8s"
    pretty_exposure_times[250000] = "1/4s"
    pretty_exposure_times[500000] = "1/2s"
    pretty_exposure_times[1000000] = "1s"
    pretty_exposure_times[2000000] = "2s"
    pretty_exposure_times[4000000] = "4s"
    pretty_exposure_times[8000000] = "8s"
    pretty_exposure_times[12000000] = "12s"
    pretty_exposure_times[16000000] = "16s"
    pretty_exposure_times[20000000] = "20s"
    pretty_exposure_times[25000000] = "25s"
    pretty_exposure_times[30000000] = "30s"
    return pretty_exposure_times


def create_folder_if_not_exists(folder_path):
    """
    Creates a folder if it doesn't already exist
    Arguments: 
    folder_path - the path of the folder
    """
    folder = Path(folder_path)
    if not folder.exists():
        folder.mkdir(parents=True, exist_ok=True)
