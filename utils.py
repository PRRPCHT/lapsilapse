from datetime import datetime
import math
import psutil
from PIL import Image, ImageStat


def get_day_and_time():
    dateTimeObj = datetime.now()
    return dateTimeObj.strftime("%Y-%m-%d %H-%M-%S")


def get_day():
    dateTimeObj = datetime.now()
    return dateTimeObj.strftime("%Y-%m-%d")


def pretty_number(number, max):
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
    exposure_time_in_seconds = int(exposure_time / 1000000)
    return expected_delay - exposure_time_in_seconds


def brightness(im_file):
    im = Image.open(im_file)
    stat = ImageStat.Stat(im)
    r, g, b = stat.mean
    return math.sqrt(0.241*(r**2) + 0.691*(g**2) + 0.068*(b**2))


def debug(message):
    log(message, "DEBUG")


def info(message):
    log(message, "INFO")


def warning(message):
    log(message, "WARNING")


def error(message):
    log(message, "ERROR")


def log(message, level):
    print(get_day_and_time() + " :: " + level + " :: " + message)


def get_cpu_temp():
    tempFile = open("/sys/class/thermal/thermal_zone0/temp")
    cpu_temp = tempFile.read()
    tempFile.close()
    return round(float(cpu_temp)/1000, 2)


def get_cpu_usage():
    return psutil.cpu_percent(interval=1)
