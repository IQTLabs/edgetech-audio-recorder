"""This file contains the AudioPubSub class which is a child class of BaseMQTTPubSub.
The AudioPubSub uses arecord and ffmpeg to record and save audio as .flac files.
"""
import json
import os
from time import sleep
from datetime import datetime
from typing import Any, Dict
import subprocess
import schedule

import paho.mqtt.client as mqtt

from base_mqtt_pub_sub import BaseMQTTPubSub


class AudioPubSub(BaseMQTTPubSub):
    """The AudioPubSub uses arecord + ffmpeg to record and save .wav audio recordings that
    are compressed to .flac files. Files are cycled by responding to C2 commands.

    Args:
        BaseMQTTPubSub (BaseMQTTPubSub): parent class written in the EdgeTech Core module.
    """

    def __init__(
        self: Any,
        send_data_topic: str,
        c2_topic: str,
        data_root: str,
        sensor_directory_name: str,
        file_prefix: str,
        debug: bool = False,
        **kwargs: Any,
    ) -> None:
        """The AudioPubSub constructor takes broadcast and subscribe topics and file paths.
        It uses arecord and ffmpeg to record .wav files and then convert them to .flac files
        after instantiating a connection to the MQTT broker and subscribes to the C2 topic
        to cycle files.

        Args:
            send_data_topic (str): the topic to broadcast the new file path every time
            generating a new file is triggered.
            c2_topic (str): the command and control topic that triggers writing to a new file.
            data_root (str): the parent directory to save the audio files to.
            sensor_directory_name (str): the directory name to create in the data_root where
            the files will be saved.
            file_prefix (str): the fixed beginning of each filename.
            debug (bool, optional): If the debug mode is turned on, log statements print to
            stdout. Defaults to False.
        """
        # to override any keyword arguments in the base class
        super().__init__(**kwargs)

        # assigining class attributes
        self.send_data_topic = send_data_topic
        self.debug = debug
        self.c2_topic = c2_topic
        self.save_path = os.path.join(data_root, sensor_directory_name)

        # compressed file related class attributes
        self.file_prefix = file_prefix
        self.file_timestamp = ""
        self.file_suffix = ".flac"
        self.file_name = self.file_prefix + self.file_timestamp + self.file_suffix
        self.file_path = ""

        # uncompressed file related class attributes
        self.temp_file_suffix = "_tmp.wav"
        self.temp_file_name = self.file_timestamp + self.temp_file_suffix
        self.temp_file_path = ""

        self.record_process = None
        self.convert_process = None

        # create save directory if it does not exist
        os.makedirs(self.save_path, exist_ok=True)

        # set gain
        os.makedirs(self.save_path, exist_ok=True)

        gain_cmd = f"/usr/bin/amixer sset ADC {30}db"
        gain_process = subprocess.Popen(
            gain_cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        gain_stdout, gain_stderr = gain_process.communicate()

        if self.debug:
            print(gain_stdout)
            print(gain_stderr)

        # MQTT client setup
        self.connect_client()
        sleep(1)
        self.publish_registration("Audio Recorder Registration")

        # trigger start recording audio
        self._record_audio()

    def _send_data(self: Any, data: Dict[str, str]) -> None:
        """Function that takes a data payload containing a timestamp and the compressed audio
        file name, then publishes this to MQTT with a JSON header.

        Args:
            data (Dict[str, str]): dictionary that contains the compressed audio file name
            and timestamp.
        """
        # create JSON header using BaseMQTTPubSub functionality
        out_json = self.generate_payload_json(
            push_timestamp=str(int(datetime.utcnow().timestamp())),
            device_type="Collector",
            id_="TEST",
            deployment_id=f"AISonobuoy-Arlington-{'TEST'}",
            current_location="-90, -180",
            status="Debug",
            message_type="Event",
            model_version="null",
            firmware_version="v0.0.0",
            data_payload_type="AudioFileName",
            data_payload=json.dumps(data),
        )

        # publish payload w/ header
        self.publish_to_topic(self.send_data_topic, out_json)

    def _record_audio(self: Any) -> None:
        """This function builds the save path for the temporary .wav file and calls arecord to
        record audio from the soundcard.
        """
        # build .wav file path
        self.file_timestamp = str(int(datetime.utcnow().timestamp()))
        self.temp_file_name = self.file_timestamp + self.temp_file_suffix
        self.temp_file_path = os.path.join(self.save_path, self.temp_file_name)

        # arecord command
        rec_cmd = (
            f"arecord -q -D sysdefault -r 44100 -f S16 -V mono {self.temp_file_path}"
        )
        # call command using python subprocess
        self.record_process = subprocess.Popen(rec_cmd.split())

    def _stop_record_audio(self: Any) -> None:
        """This function kills the arecord recording process and builds the compressed save path,
        then calls ffmpeg to convert the .wav file to a .flac file.
        """
        # kill arecord process
        self.record_process.kill()

        # build .flac file path
        self.file_name = self.file_prefix + self.file_timestamp + self.file_suffix
        self.file_path = os.path.join(self.save_path, self.file_name)

        # ffmpeg conversion from .wav to .flac command
        ffmpeg_cmd = f"ffmpeg -i {self.temp_file_path} -y -ac 1 -ar 44100 \
        -sample_fmt s16 {self.file_path}"

        # call command using subprocess
        self.convert_process = subprocess.Popen(ffmpeg_cmd.split())

    def _c2_callback(
        self: Any, _client: mqtt.Client, _userdata: Dict[Any, Any], msg: Any
    ) -> None:
        """Callback for the C2 topic which currently triggers the changing of files to write to.

        Args:
            _client (mqtt.Client): the MQTT client that was instatntiated in the constructor.
            _userdata (Dict[Any,Any]): data passed to the callback through the MQTT paho Client
            class contructor or set later through user_data_set().
            msg (Any): the recieved message over the subscribed channel that includes
            the topic name and payload after decoding. The messages here will include the
            sensor data to save.
        """
        # decode the JSON payload from callback message
        c2_payload = json.loads(str(msg.payload.decode("utf-8")))

        # if the payload is NEW FILE then stop previous recording and switch to new file
        # + compress and broadcast compression file name
        if c2_payload["msg"] == "NEW FILE":
            # stop recording + compress
            self._stop_record_audio()
            # send compressed filename

            self._send_data(
                {
                    "timestamp": str(int(datetime.utcnow().timestamp())),
                    "data": f"/home/mobian{self.file_path}",
                }
            )
            # start a new recording
            self._record_audio()

    def _cleanup_temp_files(self: Any) -> None:
        """This function is called using the scheduler module and serves as a runner
        to delete the .wav files that are no long needed.
        """

        # list of .wav files
        temp_files_ls = [
            *filter(
                lambda file: file.endswith(self.temp_file_suffix),
                os.listdir(self.save_path),
            )
        ]

        # sorting oldest newest
        temp_files_ls.sort(key=lambda x: int(x.split("_")[0]))
        # setting up all but the two newest files for deletion
        to_delete_ls = temp_files_ls[:-2]

        # delete each file in the list
        for file in to_delete_ls:
            os.remove(os.path.join(self.save_path, file))

    def main(self: Any) -> None:
        """Main loop and function that setup the heartbeat to keep the TCP/IP
        connection alive and publishes the data to the MQTT broker and keeps the
        main thread alive.
        """
        # publish hearbeat every 10 seconds to keep TCP/IP connection alive

        schedule.every(10).seconds.do(
            self.publish_heartbeat, payload="Audio Recorder Heartbeat"
        )

        # call .wav files deleter every 15 minutes
        schedule.every(15).minutes.do(self._cleanup_temp_files)

        # setup subscription to C2 topic for file cycling
        self.add_subscribe_topic(self.c2_topic, self._c2_callback)

        while True:
            try:
                # flusing pending scheduled tasks
                schedule.run_pending()
                sleep(0.001)
            except KeyboardInterrupt as exception:
                self._stop_record_audio()
                if self.debug:
                    print(exception)


if __name__ == "__main__":
    recorder = AudioPubSub(
        send_data_topic=str(os.environ.get("SEND_DATA_TOPIC")),
        c2_topic=str(os.environ.get("C2_TOPIC")),
        data_root=str(os.environ.get("DATA_ROOT")),
        sensor_directory_name=str(os.environ.get("SENSOR_DIR")),
        file_prefix=str(os.environ.get("FILE_PREFIX")),
        mqtt_ip=str(os.environ.get("MQTT_IP")),
    )
    recorder.main()
