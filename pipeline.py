# encoding=utf8
import datetime
from distutils.version import StrictVersion
import hashlib
import os.path
import random
from seesaw.config import realize, NumberConfigValue
from seesaw.externalprocess import ExternalProcess
from seesaw.item import ItemInterpolation, ItemValue
from seesaw.task import SimpleTask, LimitConcurrent
from seesaw.tracker import GetItemFromTracker, PrepareStatsForTracker, \
    UploadWithTracker, SendDoneToTracker
import shutil
import socket
import subprocess
import sys
import time
import string
from tornado import httpclient

import seesaw
from seesaw.externalprocess import WgetDownload
from seesaw.pipeline import Pipeline
from seesaw.project import Project
from seesaw.util import find_executable

# check the seesaw version
if StrictVersion(seesaw.__version__) < StrictVersion('0.8.5'):
    raise Exception('This pipeline needs seesaw version 0.8.5 or higher.')

###########################################################################
# Find a useful Wget+Lua executable.
#
# WGET_LUA will be set to the first path that
# 1. does not crash with --version, and
# 2. prints the required version string
WGET_LUA = find_executable(
    'Wget+Lua',
    ['GNU Wget 1.14.lua.20130523-9a5c', 'GNU Wget 1.14.lua.20160530-955376b'],
    [
        './wget-lua',
        './wget-lua-warrior',
        './wget-lua-local',
        '../wget-lua',
        '../../wget-lua',
        '/home/warrior/wget-lua',
        '/usr/bin/wget-lua'
    ]
)

if not WGET_LUA:
    raise Exception('No usable Wget+Lua found.')

###########################################################################
# The version number of this pipeline definition.
#
# Update this each time you make a non-cosmetic change.
# It will be added to the WARC files and reported to the tracker.
VERSION = '20190716.01'
USER_AGENT = 'ArchiveTeam'
TRACKER_ID = 'webcite'
TRACKER_HOST = 'tracker.kiska.pw'


###########################################################################
# This section defines project-specific tasks.
#
# Simple tasks (tasks that do not need any concurrency) are based on the
# SimpleTask class and have a process(item) method that is called for
# each item.
class CheckIP(SimpleTask):
    def __init__(self):
        SimpleTask.__init__(self, 'CheckIP')
        self._counter = 0

    def process(self, item):
        # NEW for 2014! Check if we are behind firewall/proxy

        if self._counter <= 0:
            item.log_output('Checking IP address.')
            ip_set = set()

            ip_set.add(socket.gethostbyname('twitter.com'))
            ip_set.add(socket.gethostbyname('facebook.com'))
            ip_set.add(socket.gethostbyname('youtube.com'))
            ip_set.add(socket.gethostbyname('microsoft.com'))
            ip_set.add(socket.gethostbyname('icanhas.cheezburger.com'))
            ip_set.add(socket.gethostbyname('archiveteam.org'))

            if len(ip_set) != 6:
                item.log_output('Got IP addresses: {0}'.format(ip_set))
                item.log_output(
                    'Are you behind a firewall/proxy? That is a big no-no!')
                raise Exception(
                    'Are you behind a firewall/proxy? That is a big no-no!')

        # Check only occasionally
        if self._counter <= 0:
            self._counter = 10
        else:
            self._counter -= 1


class PrepareDirectories(SimpleTask):
    def __init__(self, warc_prefix):
        SimpleTask.__init__(self, 'PrepareDirectories')
        self.warc_prefix = warc_prefix

    def process(self, item):
        item_name = item['item_name']
        escaped_item_name = item_name.replace(':', '_').replace('/', '_').replace('~', '_')
        dirname = '/'.join((item['data_dir'], escaped_item_name))

        if os.path.isdir(dirname):
            shutil.rmtree(dirname)

        os.makedirs(dirname)

        item['item_dir'] = dirname
        item['warc_file_base'] = '%s-%s-%s' % (self.warc_prefix, escaped_item_name[:50],
                                               time.strftime('%Y%m%d-%H%M%S'))

        open('%(item_dir)s/%(warc_file_base)s.warc.gz' % item, 'w').close()


class MoveFiles(SimpleTask):
    def __init__(self):
        SimpleTask.__init__(self, 'MoveFiles')

    def process(self, item):
        # NEW for 2014! Check if wget was compiled with zlib support
        if os.path.exists('%(item_dir)s/%(warc_file_base)s.warc' % item):
            raise Exception('Please compile wget with zlib support!')

        os.rename('%(item_dir)s/%(warc_file_base)s.warc.gz' % item,
                  '%(data_dir)s/%(warc_file_base)s.warc.gz' % item)

        shutil.rmtree('%(item_dir)s' % item)


def get_hash(filename):
    with open(filename, 'rb') as in_file:
        return hashlib.sha1(in_file.read()).hexdigest()


CWD = os.getcwd()
PIPELINE_SHA1 = get_hash(os.path.join(CWD, 'pipeline.py'))


def stats_id_function(item):
    # NEW for 2014! Some accountability hashes and stats.
    d = {
        'pipeline_hash': PIPELINE_SHA1,
        'python_version': sys.version,
    }

    return d


class WgetArgs(object):
    post_chars = string.digits + 'abcdef'

    def int_to_str(self, i):
        d, m = divmod(i, 16)
        if d > 0:
            return self.int_to_str(d) + self.post_chars[m]
        return self.post_chars[m]

    def realize(self, item):
        wget_args = [
            WGET_LUA,
            '-U', USER_AGENT,
            '-nv',
            '--no-cookies',
            '-o', ItemInterpolation('%(item_dir)s/wget.log'),
            '--no-check-certificate',
            '--output-document', ItemInterpolation('%(item_dir)s/wget.tmp'),
            '--truncate-output',
            '-e', 'robots=off',
            '--rotate-dns',
            '--no-parent',
            '--timeout', '30',
            '--tries', 'inf',
            '--span-hosts',
            '--waitretry', '30',
            '--warc-file', ItemInterpolation('%(item_dir)s/%(warc_file_base)s'),
            '--warc-header', 'operator: Archive Team',
            '--warc-header', 'theartistunion-dld-script-version: ' + VERSION,
            '--warc-header', ItemInterpolation('webcite-item: %(item_name)s')
        ]

        item_name = item['item_name']

        http_client = httpclient.HTTPClient()

        try:
            items = http_client.fetch('http://master.newsbuddy.net/webcite/' + item_name, method='GET')
        except httpclient.HTTPError as error:
            items = error.response
        if items.code != 200:
            raise Exception('Bad status code, {} for item {}.'.format(r.code, item_name))

        for url in items.body.splitlines():
            url = url.strip()
            wget_args.append(url)
        http_client.close()
        if 'bind_address' in globals():
            wget_args.extend(['--bind-address', globals()['bind_address']])
            print('')
            print('*** Wget will bind address at {0} ***'.format(
            globals()['bind_address']))
            print('')
        return realize(wget_args, item)

###########################################################################
# Initialize the project.
#
# This will be shown in the warrior management panel. The logo should not
# be too big. The deadline is optional.
project = Project(
    title='webcite',
    project_html='''
    <img class="project-logo" alt="logo" src="https://www.archiveteam.org/images/8/8a/Archivetime.png" height="50px"/>
    <h2>webcite.com <span class="links"><a href="https://www.webcite.com">Website</a> &middot; <a href="http://tracker.archiveteam.org/webcite/">Leaderboard</a></span></h2>
    '''
)

pipeline = Pipeline(
    CheckIP(),
    GetItemFromTracker('http://%s/%s' % (TRACKER_HOST, TRACKER_ID), downloader,
                       VERSION),
    PrepareDirectories(warc_prefix='webcite'),
    WgetDownload(
        WgetArgs(),
        max_tries=2,
        accept_on_exit_code=[0, 4, 8],
        env={
            'item_dir': ItemValue('item_dir'),
            'warc_file_base': ItemValue('warc_file_base'),
        }
    ),
    PrepareStatsForTracker(
        defaults={'downloader': downloader, 'version': VERSION},
        file_groups={
            'data': [
                ItemInterpolation('%(item_dir)s/%(warc_file_base)s.warc.gz')
            ]
        },
        id_function=stats_id_function,
    ),
    MoveFiles(),
    LimitConcurrent(NumberConfigValue(min=1, max=20, default='20',
                                      name='shared:rsync_threads', title='Rsync threads',
                                      description='The maximum number of concurrent uploads.'),
                    UploadWithTracker(
                        'http://%s/%s' % (TRACKER_HOST, TRACKER_ID),
                        downloader=downloader,
                        version=VERSION,
                        files=[
                            ItemInterpolation('%(data_dir)s/%(warc_file_base)s.warc.gz')
                        ],
                        rsync_target_source_path=ItemInterpolation('%(data_dir)s/'),
                        rsync_extra_args=[
                            '--recursive',
                            '--partial',
                            '--partial-dir', '.rsync-tmp',
                        ]
                    ),
                    ),
    SendDoneToTracker(
        tracker_url='http://%s/%s' % (TRACKER_HOST, TRACKER_ID),
        stats=ItemValue('stats')
    )
)
