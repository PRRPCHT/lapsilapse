from datetime import datetime
import io
import json
import logging
import os
import re
import shutil
import threading
import time
from typing import Dict
from flask import Flask, Response, jsonify, render_template, request
from picamera2 import Picamera2, Controls
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput
from threading import Condition
from settings import Settings
from timelapse import Timelapse, TimelapseGallery
from utils import brightness, get_cpu_temp, get_cpu_usage, get_day, get_day_and_time, pretty_number, get_awb_mode, generate_pretty_exposure_times, create_folder_if_not_exists, make_thumbnail
from photo_repository import PhotoRepository, Photo

settings = Settings()
settings.load_from_json()
static_dir = "./static/"
settings.photo_directory = static_dir if settings.photo_directory is None else settings.photo_directory
target_dir = settings.photo_directory
static_photos_dir = os.path.join(static_dir, "photos/")
target_photos_dir = os.path.join(target_dir, "photos/")
thumbnails_dir = os.path.join(static_photos_dir, "thumbnails/")
static_timelapse_dir = os.path.join(static_dir, "timelapses/")
target_timelapse_dir = os.path.join(target_dir, "timelapses/")
create_folder_if_not_exists(static_photos_dir)
create_folder_if_not_exists(target_photos_dir)
create_folder_if_not_exists(thumbnails_dir)
create_folder_if_not_exists(static_timelapse_dir)
create_folder_if_not_exists(target_timelapse_dir)
create_folder_if_not_exists("./logs")

Picamera2.set_logging(Picamera2.ERROR)
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s :: %(levelname)s :: %(message)s', filename='logs/' + get_day() + '.log')
logger = logging.getLogger(__name__)
app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"]
camera = Picamera2()
pretty_exposure_times_list = generate_pretty_exposure_times()
photo_repository = PhotoRepository(static_photos_dir)
photo_repository.load_from_json()
timelapse_galleries = TimelapseGallery(static_timelapse_dir)
is_timelapse_ongoing = False
timelapse: Timelapse = None


@app.route("/shoot")
def shoot():
    """ Handles the display of the shoot page """
    global camera
    global logger
    camera.stop()
    return render_template('shoot.html', active=" shoot")


@app.route("/settings")
def showSettings():
    """ Handles the display of the settings page """
    return render_template('settings.html', active=" settings", settings=settings)


@app.route("/saveSettings", methods=['POST'])
def saveSettings():
    toReturn = {"error": False}
    try:
        input = request.get_json(force=True)
        settings.photo_directory = input["photosDirectory"]
        settings.save_to_json()
    except RuntimeError as e:
        logger.warning(str(e))
        toReturn["error"] = True
    return jsonify(toReturn)


@app.route("/gallery")
def gallery():
    """ Handles the display of the photo gallery page """
    gallery = photo_repository.organize_photos_by_date()
    return render_template('gallery.html', active=" photoGallery", gallery=gallery)


@app.route("/timelapse-gallery")
def timelapse_gallery():
    """ Handles the display of the timelpase gallery page """
    sorted_galleries = sorted(timelapse_galleries.galleries.items(
    ), key=lambda item: datetime.strptime(item[0], '%Y-%m-%d_%H-%M-%S'))
    display_galleries = [gallery for _, gallery in sorted_galleries]
    return render_template('timelapse-gallery.html', active=" timelapseGallery", gallery=display_galleries)


@app.route("/timelapse-gallery/view/<timelapse>")
def view(timelapse):
    """ Handles the display of the timelapse gallery page """
    display_timelapse = timelapse_galleries.galleries[timelapse]
    logger.info("display_timelapse.thumbnails_files")
    logger.info(display_timelapse.thumbnails_files)
    return render_template('view-timelapse.html', active=" timelapseGallery", timelapse=display_timelapse)


@app.route("/")
@app.route("/preview")
def preview():
    """ Handles the display of the preview page """
    return render_template('preview.html', active=" preview")


@app.route("/timelapse")
def show_timelapse():
    """ Handles the display of the timelapse page """
    return render_template('timelapse.html', active=" timelapse")


@app.route("/is_timelapse_ongoing")
def is_timelapse_running():
    """ Checks if the timelapse is still ongoing """
    global is_timelapse_ongoing
    to_return = {}
    to_return["is_timelapse_ongoing"] = is_timelapse_ongoing
    return jsonify(to_return)


@app.route("/stop_timelapse")
def stop_timelapse():
    """ Stops the ongoing timelapse """
    global is_timelapse_ongoing
    is_timelapse_ongoing = False
    to_return = {}
    to_return["is_timelapse_ongoing"] = is_timelapse_ongoing
    return jsonify(to_return)


@app.route("/update_timelapse")
def update_timelapse():
    """ Updates the timelapse page. Returns the full stats so that the timelpase can be displayed on any device calling this API. """
    global timelapse
    global is_timelapse_ongoing
    to_return = {}
    if is_timelapse_ongoing and (timelapse is not None):
        # to_return["reference_photo"] = "/ref.jpg"
        to_return["photos"] = timelapse.photos_list
        to_return["photos_to_take"] = timelapse.photos_to_take
        to_return["photos_taken"] = len(timelapse.photos_list)
        to_return["thumbs"] = timelapse.thumbs_list
        to_return["cpu_temp"] = get_cpu_temp()
        to_return["cpu_usage"] = get_cpu_usage()
    to_return["is_timelapse_ongoing"] = is_timelapse_ongoing
    return jsonify(to_return)


class StreamingOutput(io.BufferedIOBase):
    """ Used for camera streaming on the preview page """

    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


def genFrames():
    """ Generates the frames to be streamed """
    global camera
    output = StreamingOutput()
    camera.configure(camera.create_video_configuration(
        main={"size": (1280, 960)}))
    output = StreamingOutput()
    camera.start_recording(JpegEncoder(), FileOutput(output))
    while True:
        with output.condition:
            output.condition.wait()
            frame = output.frame
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


@app.route('/video_feed')
def video_feed():
    """ Provides the source of the stream on the preview page """
    return Response(genFrames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/doshoot', methods=['POST'])
def do_shoot():
    """ 
    Handles the shot button on the shoot page 
    Arguments (request body): 
    iso - the ISO to set
    speed - the exposure time to set in ms
    wb - the white balance to set
    file_format - the file format to save the photo in
    """
    global pretty_exposure_times_list
    toReturn = {}
    try:
        input = request.get_json(force=True)
        iso = input["iso"]
        exposure_time = input["exposureTime"]
        wb = input["wb"]
        file_format = input["fileFormat"]

        capture_config = camera.create_still_configuration(
            raw={}, display=None)
        if iso != "Auto":
            camera.set_controls({"AnalogueGain": int(iso) / 100})
        if exposure_time != -1:
            camera.set_controls({"ExposureTime": int(exposure_time)})
        if wb != "auto":
            camera.set_controls({"AwbMode": get_awb_mode(wb)})
        camera.start()
        time.sleep(2)
        r = camera.switch_mode_capture_request_and_stop(capture_config)
        day = get_day()
        day_and_time = get_day_and_time()
        jpg_path = day_and_time + ".jpg"
        jpg_full_path = os.path.join(target_photos_dir, jpg_path)
        r.save("main", jpg_full_path)
        thumbnail_full_path = os.path.join(thumbnails_dir, jpg_path)
        make_thumbnail(jpg_full_path, thumbnail_full_path, 1000, 1000)
        if "jpg" not in file_format:
            do_delete_photo(jpg_full_path)
        dng_path = None
        if "dng" in file_format:
            dng_path = day_and_time + ".dng"
            r.save_dng(target_photos_dir + dng_path)
            toReturn["dngPath"] = dng_path
        toReturn["fileName"] = day_and_time
        toReturn["iso"] = iso
        toReturn["exposureTime"] = pretty_exposure_times_list[int(
            exposure_time)]
        toReturn["wb"] = wb.capitalize()
        toReturn["jpgPath"] = jpg_path
        toReturn["thumbPath"] = jpg_path
        photo = Photo(name=day_and_time, iso=iso, speed=exposure_time, exposure_time=pretty_exposure_times_list[int(exposure_time)],
                      white_balance=wb.capitalize(), capture_date=day, jpg_path=jpg_path, dng_path=dng_path)
        photo_repository.add_photo(photo)
    except RuntimeError as e:
        logger.warning(str(e))
        toReturn["error"] = True
    return jsonify(toReturn)


@app.route("/deletephoto", methods=['POST'])
def delete_photo():
    """ 
    Deletes all versions of a photo - both JPG and DNG versions
    Arguments (request body): 
    name - the name of the photo
    """
    toReturn = {}
    input = request.get_json(force=True)
    try:
        name = input["name"]
        photo = photo_repository.get_photo(name)
    except:
        toReturn["error"] = True
        return jsonify(toReturn)
    try:
        jpg_path = static_photos_dir + photo.jpg_path
    except:
        jpg_path = None
    is_jpg_deletion_error = not do_delete_photo(jpg_path)
    try:
        dng_path = static_photos_dir + photo.dng_path
    except:
        dng_path = None
    is_dng_deletion_error = not do_delete_photo(dng_path)
    toReturn["error"] = is_jpg_deletion_error or is_dng_deletion_error
    if not toReturn["error"]:
        photo_repository.remove_photo(name)
        thumbnail_path = os.path.join(thumbnails_dir, name + ".jpg")
        do_delete_photo(thumbnail_path)
    return jsonify(toReturn)


def do_delete_photo(photo_path) -> bool:
    """ 
    Deletes a photo
    Arguments: 
    photo_path - the path of the photo
    Returns:
    True if the deletion was a success or if the path was None.
    """
    if photo_path != None and os.path.exists(photo_path):
        try:
            os.remove(photo_path)
            logger.info("Deleted photo: " + photo_path)
            return True
        except:
            logger.error("Error while deleting: " + photo_path)
            return False
    else:
        return True


@app.route("/deletetimelapse", methods=['POST'])
def delete_timelapse():
    """ 
    Deletes a timelapse
    Arguments (request body): 
    timelapse - the name of the timelapse
    """
    toReturn = {}
    toReturn["error"] = False
    input = request.get_json(force=True)
    timelapse: str = input["timelapse"]
    static_timelapse_path = os.path.join(static_timelapse_dir, timelapse)
    if timelapse != None and os.path.exists(static_timelapse_path):
        try:
            shutil.rmtree(static_timelapse_path)
            logger.info("Timelapse deleted: " + timelapse)

        except:
            toReturn["error"] = True
            return jsonify(toReturn)
        if not toReturn["error"]:
            timelapse_galleries.remove(timelapse)
    return jsonify(toReturn)


def run_timelapse(input):
    """ 
    Runs the timelapse - is meant to be ran in a thread
    Arguments: 
    input - the parameters of the timelapse - see the Timelapse class
    """
    global is_timelapse_ongoing
    global timelapse
    logger.info("Start timelapse")
    date_and_time = get_day_and_time()
    static_working_dir = os.path.join(static_timelapse_dir, date_and_time)
    # relative_tmp_dir = date_and_time + "/tmp/"
    os.makedirs(static_working_dir, exist_ok=True)
    tmp_dir = os.path.join(static_working_dir, "tmp")
    logger.info(tmp_dir)
    os.makedirs(tmp_dir, exist_ok=True)
    target_working_dir = os.path.join(target_timelapse_dir, date_and_time)
    os.makedirs(target_working_dir, exist_ok=True)

    timelapse = Timelapse(input)
    is_timelapse_ongoing = True
    timelapse_galleries.add_timelapse(date_and_time)

    preview_config = camera.create_preview_configuration()
    capture_config = camera.create_still_configuration(
        raw={"size": camera.sensor_resolution})
    camera.stop()
    camera.configure(preview_config)
    camera.set_controls({"AnalogueGain": timelapse.iso / 100})
    camera.set_controls({"ExposureTime": timelapse.exposure_time})
    camera.set_controls({"AwbMode": timelapse.wb})
    camera.start()
    time.sleep(2)
    reference_path = os.path.join(tmp_dir, "ref.jpg")
    while is_timelapse_ongoing and timelapse.is_ongoing():
        take_timelapse_photo(capture_config, reference_path,
                             target_working_dir, tmp_dir, date_and_time)
        logger.info("Sleeping for: " + str(timelapse.get_sleep_time()))
        time.sleep(timelapse.get_sleep_time())
    camera.stop()
    time.sleep(2)
    os.remove(reference_path)
    is_timelapse_ongoing = False
    logger.info("Timelapse finished")


def take_timelapse_photo(capture_config: Dict, reference_path: str, working_dir: str, tmp_dir: str, date_and_time: str):
    """ 
    Takes a photo for the ongoin timelapse
    Arguments: 
    capture_config (Dict) - the capture configuration for the camera
    reference_path (str) - the path to the reference file for brightness calculation
    working_dir (str) - the path to the working directory
    tmp_dir (str) - the path to the tmp directory
    date_and_time (str) - the start date and time of the timelapse
    """
    camera.stop()
    camera.set_controls({"AnalogueGain": timelapse.iso / 100})
    camera.set_controls({"ExposureTime": timelapse.exposure_time})
    camera.start()
    timelapse.photos_taken = timelapse.photos_taken + 1
    logger.info("==================== Taking photo: " + str(timelapse.photos_taken) +
                "/" + str(timelapse.photos_to_take))
    filename = "tl_" + \
        pretty_number(timelapse.photos_taken, timelapse.photos_to_take) + \
        "_" + get_day_and_time() + "_ISO_" + str(timelapse.iso) + "_" + \
        pretty_exposure_times_list[timelapse.exposure_time].replace(
            '/', '-')
    r = camera.switch_mode_capture_request_and_stop(capture_config)
    r.save("main", reference_path)
    if "dng" in timelapse.file_format:
        dng_path = os.path.join(working_dir, filename + ".dng")
        r.save_dng("main", dng_path)
        timelapse_galleries.add_dng(date_and_time, dng_path)
    jpg_path = os.path.join(working_dir, filename + ".jpg")
    r.save("main", jpg_path)
    photo_brightness = brightness(reference_path)
    day_and_time = get_day_and_time()
    timelapse.add_photo(filename, day_and_time, photo_brightness)
    timelapse.update_settings(photo_brightness)
    thumbnail_path = os.path.join(tmp_dir, filename + ".jpg")
    make_thumbnail(jpg_path, thumbnail_path, 400, 400)
    timelapse.add_thumbnail(
        path=thumbnail_path, day_and_time=day_and_time, number=timelapse.photos_taken, iso=timelapse.iso, speed=pretty_exposure_times_list[timelapse.exposure_time], brightness=photo_brightness)
    timelapse_galleries.add_thumbnail(date_and_time, thumbnail_path)
    if "jpg" not in timelapse.file_format:
        do_delete_photo(jpg_path)
    else:
        timelapse_galleries.add_jpg(date_and_time, jpg_path)


@app.route('/start_timelapse', methods=['POST'])
def start_timelapse():
    """ 
    Starts the timelapse in a dedicated thread
    Arguments (request body): 
    input - the parameters of the timelapse - see the Timelapse class
    """
    to_return = {}
    to_return["started"] = False
    if not is_timelapse_ongoing:
        try:
            input = request.get_json(force=True)
            x = threading.Thread(target=run_timelapse,
                                 args=(input,), daemon=True)
            x.start()
            to_return["started"] = True
        except RuntimeError as e:
            logger.warning(str(e))
            to_return["error"] = str(e)
    return jsonify(to_return)


def data_from_name(filename: str):
    """
    Extracts data from a timelapse file name.
    Args:
    filename (str): The filename to be analysed.
    Returns: A dict containing:
    - number: the number of the photo in the sequence, 
    - date: the date the photo was taken,
    - time: the time the photo was taken,
    - iso: the ISO value,
    - exposure_time: the exposure time.
    """
    logger.info("In data_from_name")
    logger.info(filename)
    pattern = "tl_([0-9]+)_([0-9]{4}-[0-9]{2}-[0-9]{2})_([0-9]{2}-[0-9]{2}-[0-9]{2})_ISO_([0-9]+)_([0-9s-]+).jpg"
    match = re.match(pattern, filename)
    if match:
        number, date, time, iso, exposure_time = match.groups()
        return {
            'number': number,
            'date': date,
            'time': time,
            'iso': iso,
            'exposure_time': exposure_time
        }
    pattern = r"tl_([0-9]+)\.jpg"
    match = re.match(pattern, filename)
    if match:
        number = match.groups()
        return {
            'number': number,
            'date': None,
            'time': None,
            'iso': None,
            'exposure_time': None
        }
    return None


def format_exposure_time(exposure_time: str) -> str:
    """
    Replaces all instances of '-' with '/' in the provided exposure_time.
    Args:
    exposure_time (str): The string in which to replace dashes with slashes.
    Returns:
    str: The modified string with dashes replaced by slashes.
    """
    if exposure_time is not None:
        modified_string = exposure_time.replace('-', '/')
        return modified_string
    return None


app.jinja_env.filters.update(data_from_name=data_from_name)
app.jinja_env.filters.update(format_exposure_time=format_exposure_time)
