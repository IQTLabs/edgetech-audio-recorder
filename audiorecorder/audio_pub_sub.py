import time
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
    def __init__(
        self,
        send_data_topic: str,
        c2c_topic: str,
        data_root: str,
        sensor_directory_name: str,
        file_prefix: str,
        debug: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)

        self.send_data_topic = send_data_topic
        self.debug = debug
        self.c2c_topic = c2c_topic
        self.save_path = os.path.join(data_root, sensor_directory_name)

        self.file_prefix = file_prefix
        self.file_timestamp = ""
        self.file_suffix = ".flac"
        self.file_name = self.file_prefix + self.file_timestamp + self.file_suffix
        self.file_path = ""

        self.temp_file_suffix = "_tmp.wav"
        self.temp_file_name = self.file_timestamp + self.temp_file_suffix
        self.temp_file_path = ""

        self.record_process = None

        os.makedirs(self.save_path, exist_ok=True)

        gain_cmd = f"/usr/bin/amixer sset ADC {30}db"
        gain_process = subprocess.Popen(
            gain_cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        gain_stdout, gain_stderr = gain_process.communicate()

        if self.debug:
            print(gain_stdout)
            print(gain_stderr)

        self.connect_client()
        sleep(1)
        self.publish_registration("Audio Recorder Registration")

        self._record_audio()

    def _send_data(self, data) -> None:
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

        self.publish_to_topic(self.send_data_topic, out_json)

    def _record_audio(self: Any) -> None:
        self.file_timestamp = str(int(datetime.utcnow().timestamp()))
        self.temp_file_name = self.file_timestamp + self.temp_file_suffix
        self.temp_file_path = os.path.join(self.save_path, self.temp_file_name)
        rec_cmd = (
            f"arecord -q -D sysdefault -r 44100 -f S16 -V mono {self.temp_file_path}"
        )
        self.record_process = subprocess.Popen(rec_cmd.split())

    def _stop_record_audio(self: Any) -> None:
        self.record_process.kill()

        self.file_name = self.file_prefix + self.file_timestamp + self.file_suffix
        self.file_path = os.path.join(self.save_path, self.file_name)

        ffmpeg_cmd = f"ffmpeg -i {self.temp_file_path} -y -ac 1 -ar 44100 \
        -sample_fmt s16 {self.file_path}"
        subprocess.Popen(ffmpeg_cmd.split())

    def _c2c_callback(
        self: Any, _client: mqtt.Client, _userdata: Dict[Any, Any], msg: Any
    ) -> None:
        c2c_payload = json.loads(str(msg.payload.decode("utf-8")))
        if c2c_payload["msg"] == "NEW FILE":
            self._stop_record_audio()
            self._send_data(
                {
                    "timestamp": str(int(datetime.utcnow().timestamp())),
                    "data": f"/home/mobian{self.file_path}",
                }
            )
            self._record_audio()

    def _cleanup_temp_files(self: Any) -> None:

        temp_files_ls = [
            *filter(
                lambda file: file.endswith(self.temp_file_suffix),
                os.listdir(self.save_path),
            )
        ]

        temp_files_ls.sort(key=lambda x: int(x.split("_")[0]))
        to_delete_ls = temp_files_ls[:-2]

        for file in to_delete_ls:
            os.remove(os.path.join(self.save_path, file))

    def main(self: Any) -> None:

        schedule.every(10).seconds.do(
            self.publish_heartbeat, payload="Audio Recorder Heartbeat"
        )

        schedule.every(15).minutes.do(self._cleanup_temp_files)

        self.add_subscribe_topic(self.c2c_topic, self._c2c_callback)

        while True:
            try:
                schedule.run_pending()
                time.sleep(0.001)
            except KeyboardInterrupt:
                self._stop_record_audio()
                if self.debug:
                    print("audio-recorder application stopped!")

            except Exception as e:
                self._stop_record_audio()
                if self.debug:
                    print(e)


if __name__ == "__main__":
    recorder = AudioPubSub(
        send_data_topic=os.environ.get("SEND_DATA_TOPIC"),
        c2c_topic=os.environ.get("C2_TOPIC"),
        data_root=os.environ.get("DATA_ROOT"),
        sensor_directory_name=os.environ.get("SENSOR_DIR"),
        file_prefix=os.environ.get("FILE_PREFIX"),
        mqtt_ip=os.environ.get("MQTT_IP"),
    )
    recorder.main()
