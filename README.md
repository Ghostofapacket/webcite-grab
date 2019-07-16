NewsGrabber-Deduplication
=============

More information about the archiving project can be found on the ArchiveTeam wiki: [NewsGrabber](http://archiveteam.org/index.php?title=NewsGrabber)

Setup instructions
=========================

As this is purely a cleanup project, it won't be run as part of the distributed warrior deployment. This project will require at least 150G of space **PER ITEM** - Some of the warcs we are dealing with are 100G in size and we need to assume a minimum of 50% space saving at this time.

Be sure to replace `YOURNICKHERE` with the nickname that you want to be shown as, on the tracker. You don't need to register it, just pick a nickname you like.

Running with docker
--------------------

<img alt="Docker logo" src="https://upload.wikimedia.org/wikipedia/commons/7/79/Docker_%28container_engine%29_logo.png" height="100px">

Assuming this is a stand alone box, not part of a swarm etc, basic instructions for configuring your docker instance can be found at [docker documentation](https://docs.docker.com/install/) or for [Ubuntu](https://docs.docker.com/install/linux/docker-ce/ubuntu/) / [Debian](https://docs.docker.com/install/linux/docker-ce/debian/).

Make a directory, cd into the directry and copy the included dockerfile into it; the rest of the files are not required. Edit the final line to include the concurrency (CPU bound due to the deduplication, recommend 1.5 times CPU / vCPU) and replace `UnknownDocker` with your username.

Build the container with the following arguments;

    docker build -t <<dockername>> <<foldername>>/

for example

    docker build -t newsgrabber-deduplicate newsgrabber-deduplicate/
    
Then simply run the container with either;

    docker run -d -it newsgrabber-deduplicate

or if you want to give it a known name and make it easier to run commands;

    docker run -d -it --name newsgrabber-deduplicate newsgrabber-deduplicate

or if you really want that web page to be available;

    docker run -d -it -p 8001:8001 --name newsgrabber-deduplicate newsgrabber-deduplicate

Stopping the container (clean);

    docker run -d -it --name <<containername>> touch STOP

Stopping the container (hard);

    docker stop <<containername>>

Connecting to the container console;

    docker attach <<containername>>