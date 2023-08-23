import io
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
from utils import brightness, get_cpu_temp, get_cpu_usage, get_day, get_day_and_time, pretty_number

Picamera2.set_logging(Picamera2.ERROR)
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s :: %(levelname)s :: %(message)s', filename=get_day() + '.log')
logger = logging.getLogger(__name__)
app = Flask(__name__)
camera = Picamera2()
static_dir = "./static/"

is_timelapse_ongoing = False
timelapse: Timelapse = None


@app.route("/shoot")
def shoot():
    """ Handles the display of the shoot page """
    global camera
    global logger
    camera.stop()
    day = get_day()
    working_dir = static_dir + day
    os.makedirs(working_dir, exist_ok=True)
    dir_list = os.listdir(os.path.join(static_dir, day))
    dir_list.sort(reverse=True)
    photos = []
    for item in dir_list:
        if item.endswith(".jpg"):
            photo = {}
            photo["jpg_path"] = os.path.join(day, item)
            photo["file_name"] = item[:-4]
            photos.append(photo)
    # photos.reverse()
    return render_template('shoot.html', active=" shoot", photos=photos)


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
    toReturn = {}
    try:
        input = request.get_json(force=True)
        iso = input["iso"]
        speed = input["speed"]
        wb = input["wb"]
        # custom_wb = input["custom_wb"]
        file_format = input["file_format"]

        preview_config = camera.create_preview_configuration()
        capture_config = camera.create_still_configuration(
            raw={}, display=None)
        ctrls = Controls(camera)
        # ctrls.WhiteBalance = "Sunny"

        camera.start()
        time.sleep(2)
        r = camera.switch_mode_capture_request_and_stop(capture_config)
        day = get_day()
        day_and_time = get_day_and_time()
        os.makedirs(static_dir + day, exist_ok=True)
        jpg_path = day + "/" + day_and_time + ".jpg"
        r.save("main", static_dir + jpg_path)
        if file_format == "DNG":
            dng_path = day + "/" + day_and_time + ".dng"
            r.save_dng(static_dir + dng_path)

            toReturn["dng_path"] = dng_path
        toReturn["file_name"] = day_and_time
        toReturn["iso"] = iso
        toReturn["speed"] = speed
        toReturn["wb"] = wb
        toReturn["jpg_path"] = jpg_path
    except RuntimeError as e:
        logger.warning(str(e))
        toReturn["error"] = True
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
    working_dir = static_dir + date_and_time + "/"
    relative_tmp_dir = date_and_time + "/tmp/"
    os.makedirs(working_dir, exist_ok=True)
    tmp_dir = static_dir + relative_tmp_dir
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
