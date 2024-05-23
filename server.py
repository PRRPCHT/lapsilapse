import io
import json
import logging
import os
import threading
import time
from flask import Flask, Response, jsonify, render_template, request
from picamera2 import Picamera2, Controls
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput
from threading import Condition
from timelapse import Timelapse
from utils import brightness, get_cpu_temp, get_cpu_usage, get_day, get_day_and_time, pretty_number, get_awb_mode, generate_pretty_exposure_times, create_folder_if_not_exists
from photo_repository import PhotoRepository, Photo

create_folder_if_not_exists("./static/photos")
create_folder_if_not_exists("./static/timelapse")
create_folder_if_not_exists("./logs")

Picamera2.set_logging(Picamera2.ERROR)
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s :: %(levelname)s :: %(message)s', filename='logs/' + get_day() + '.log')
logger = logging.getLogger(__name__)
app = Flask(__name__)
camera = Picamera2()
static_dir = "./static/"
photos_dir = static_dir + "photos/"
timelapse_dir = static_dir + "timelapse/"
pretty_exposure_times_list = generate_pretty_exposure_times()
photo_repository = PhotoRepository(photos_dir)
photo_repository.load_from_json()

is_timelapse_ongoing = False
timelapse: Timelapse = None


@app.route("/shoot")
def shoot():
    """ Handles the display of the shoot page """
    global camera
    global logger
    camera.stop()
    day = get_day()
    return render_template('shoot.html', active=" shoot")


@app.route("/gallery")
def gallery():
    """ Handles the display of the gallery page """
    gallery = photo_repository.organize_photos_by_date()
    return render_template('gallery.html', active=" gallery", gallery=gallery)


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
        # custom_wb = input["custom_wb"]
        file_format = input["fileFormat"]

        capture_config = camera.create_still_configuration(
            raw={}, display=None)
        if iso != "auto":
            camera.set_controls({"AnalogueGain": int(iso) / 100})
        if exposure_time != "auto":
            camera.set_controls({"ExposureTime": int(exposure_time)})
        if wb != "auto":
            camera.set_controls({"AwbMode": get_awb_mode(wb)})
        camera.start()
        time.sleep(2)
        r = camera.switch_mode_capture_request_and_stop(capture_config)
        day = get_day()
        day_and_time = get_day_and_time()
        # os.makedirs(photos_dir + day, exist_ok=True)
        # jpg_path = day + "/" + day_and_time + ".jpg"
        jpg_path = day_and_time + ".jpg"
        r.save("main", photos_dir + jpg_path)
        dng_path = None
        if "dng" in file_format:
            # dng_path = day + "/" + day_and_time + ".dng"
            dng_path = day_and_time + ".dng"
            r.save_dng(photos_dir + dng_path)
            toReturn["dngPath"] = dng_path
        toReturn["fileName"] = day_and_time
        toReturn["iso"] = iso
        toReturn["exposureTime"] = pretty_exposure_times_list[int(
            exposure_time)]
        toReturn["wb"] = wb.capitalize()
        toReturn["jpgPath"] = jpg_path
        photo = Photo(name=day_and_time, iso=iso, speed=exposure_time, exposure_time=pretty_exposure_times_list[int(exposure_time)],
                      white_balance=wb.capitalize(), capture_date=day, jpg_path=jpg_path, dng_path=dng_path)
        photo_repository.add_photo(photo)
    except RuntimeError as e:
        logger.warning(str(e))
        toReturn["error"] = True
    return jsonify(toReturn)


@app.route("/deletephoto_old", methods=['POST'])
def delete_photo_old():
    """ 
    Deletes all versions of a photo - both JPG and DNG versions
    Arguments (request body): 
    jpgPath - the path of the JPG file
    dngPath - the path of the DNG file
    """
    toReturn = {}
    input = request.get_json(force=True)
    try:
        jpg_path = photos_dir + input["jpgPath"]
    except:
        jpg_path = None
    is_jpg_deletion_error = not do_delete_photo(jpg_path)
    try:
        dng_path = photos_dir + input["dngPath"]
    except:
        dng_path = None
    is_dng_deletion_error = not do_delete_photo(dng_path)
    toReturn["error"] = is_jpg_deletion_error or is_dng_deletion_error
    if not toReturn["error"]:
        photo_repository.remove_photo()
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
        logger.info("Photo to delete: " + name)
    except:
        toReturn["error"] = True
        return jsonify(toReturn)
    try:
        jpg_path = photos_dir + photo.jpg_path
    except:
        jpg_path = None
    is_jpg_deletion_error = not do_delete_photo(jpg_path)
    try:
        dng_path = photos_dir + photo.dng_path
    except:
        dng_path = None
    is_dng_deletion_error = not do_delete_photo(dng_path)
    toReturn["error"] = is_jpg_deletion_error or is_dng_deletion_error
    if not toReturn["error"]:
        photo_repository.remove_photo(name)
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
    working_dir = timelapse_dir + date_and_time + "/"
    relative_tmp_dir = date_and_time + "/tmp/"
    os.makedirs(working_dir, exist_ok=True)
    tmp_dir = timelapse_dir + relative_tmp_dir
    os.makedirs(tmp_dir, exist_ok=True)

    timelapse = Timelapse(input)
    is_timelapse_ongoing = True

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
    while is_timelapse_ongoing and timelapse.is_ongoing():
        camera.stop()
        camera.set_controls({"AnalogueGain": timelapse.iso / 100})
        camera.set_controls({"ExposureTime": timelapse.exposure_time})
        camera.start()
        timelapse.photos_taken = timelapse.photos_taken + 1
        logger.info("==================== Taking photo: " + str(timelapse.photos_taken) +
                    "/" + str(timelapse.photos_to_take))
        filename = "tl_" + \
            pretty_number(timelapse.photos_taken, timelapse.photos_to_take)
        r = camera.switch_mode_capture_request_and_stop(capture_config)
        r.save("main", tmp_dir + "ref.jpg")
        if "dng" in timelapse.file_format:
            r.save_dng(working_dir + filename + ".dng")
        if "jpg" in timelapse.file_format:
            r.save("main", working_dir + filename + ".jpg")
        photo_brightness = brightness(
            tmp_dir + "ref.jpg")
        day_and_time = get_day_and_time()
        timelapse.add_photo(filename, day_and_time, photo_brightness)
        timelapse.update_settings(photo_brightness)
        if (timelapse.can_make_thumbnail()):
            r.save("main", tmp_dir + filename + ".jpg")
            timelapse.add_thumbnail(
                relative_tmp_dir + filename + ".jpg", day_and_time)
        logger.info("Sleeping for: " + str(timelapse.get_sleep_time()))
        time.sleep(timelapse.get_sleep_time())
    camera.stop()
    time.sleep(2)
    is_timelapse_ongoing = False
    logger.info("Timelapse finished")


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
