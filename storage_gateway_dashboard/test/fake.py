# Copyright 2012 Nebula, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


class VolumeResource(object):
    def __init__(self, id=None, name=None, az=None):
        super(VolumeResource, self).__init__()
        self.attachments = []
        self.status = "enabled"
        self.replication_status = "available"
        self.id = id or "testvol"
        self.name = name or"testname"
        self.availability_zone = az or "testaz"

    def __getattr__(self, k):
        return "test"


class ReplicationResource(object):
    def __init__(self, id=None, name=None):
        super(ReplicationResource, self).__init__()
        self.status = "enabled"
        self._master = VolumeResource(id="vol1", name="maser", az="az1")
        self._slave = VolumeResource(id="vol2", name="slave", az="az2")
        self.id = id or "testrep"
        self.name = name or "testname"

    def __getattr__(self, k):
        return "test"


class BackupResource(object):
    def __init__(self):
        super(BackupResource, self).__init__()
        self.status = "available"
        self.volume = VolumeResource(id="vol3", name="forbackup", az="az1")
        self.id = "testbackup"
        self.name = "testname"

    def __getattr__(self, k):
        return "test"


class SnapshotResource(object):
    def __init__(self):
        super(SnapshotResource, self).__init__()
        self.status = "available"
        self._volume = VolumeResource(id="vol4", name="forsnapshot", az="az1")
        self.id = "testsnap"
        self.name = "testname"

    def __getattr__(self, k):
        return "test"


class CheckpointResource(object):
    def __init__(self):
        super(CheckpointResource, self).__init__()
        self.status = "available"
        self._replication = ReplicationResource(id="testrep", name="forcpt")
        self.id = "testcheckpoint"
        self.name = "testname"
        self.replication_id = "testrep"

    def __getattr__(self, k):
        return "test"
