# nosemgrep:github.workflows.config.dockerfile-source-not-pinned
FROM python:3.11
##RUN apk update && apk add alsa-utils alsa-utils-doc alsa-lib alsaconf alsa-ucm-conf bash ffmpeg
RUN apt update && apt install -y alsa-utils alsa-tools ffmpeg
RUN addgroup root audio
COPY asound.conf /etc/asound.conf
COPY record.sh /record.sh
ARG VERSION
ENV VERSION $VERSION
# nosemgrep:github.workflows.config.missing-user
#ENTRYPOINT ["/record.sh"]
# nosemgrep:github.workflows.config.missing-user
CMD ["python3","audio-record.py"]
