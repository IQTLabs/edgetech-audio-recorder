FROM iqtlabs/edgetech-core:latest
RUN apt update && apt install -y alsa-utils alsa-tools ffmpeg libportaudio2
RUN addgroup root audio
COPY asound.conf /etc/asound.conf
ARG VERSION
ENV VERSION $VERSION
COPY ./requirements.txt .
RUN pip3 install -r requirements.txt
COPY ./audio_pub_sub.py .
ENTRYPOINT [ "python3", "-u", "audio_pub_sub.py" ]