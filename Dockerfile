FROM python:3.4
ENV LC_ALL=C.UTF-8
RUN apt update \
 && apt install -y --no-install-recommends rsync git-core libssl-dev bzip2 \
 && pip install --upgrade seesaw requests warcio psutil internetarchive
ARG repo=https://github.com/Ghostofapacket/NewsGrabber-Deduplicate
ARG branch=master
RUN git clone "${repo}" grab \
 && cd grab \
 && git checkout "${branch}"
WORKDIR /grab
STOPSIGNAL SIGINT
ENTRYPOINT ["run-pipeline3", "--disable-web-server", "pipeline.py", "--max-items", "1", "USERNAME"]
