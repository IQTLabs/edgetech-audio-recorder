FROM iqtlabs/edgetech-core:latest
RUN apt update && apt install -y alsa-utils alsa-tools ffmpeg libportaudio2
RUN adduser root audio
COPY asound.conf /etc/asound.conf
COPY pyproject.toml .
COPY poetry.lock .
RUN pip3 install poetry==1.1.5
RUN poetry config virtualenvs.create false
RUN poetry install --no-dev
COPY ./audio_pub_sub.py .
ENTRYPOINT [ "python3", "audio_pub_sub.py" ]