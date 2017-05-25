# Copyright (c) 2017 Huawei, Inc.
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

from django.conf import settings
from django.utils.translation import ugettext_lazy as _

from horizon import exceptions
from horizon.utils import functions as utils
from oslo_log import log as logging

from openstack_dashboard.api import base
from openstack_dashboard.api import nova
from openstack_dashboard.contrib.developer.profiler import api as profiler
from sgsclient import client


LOG = logging.getLogger(__name__)

VOLUME_STATE_ENABLED = "enabled"
VOLUME_STATE_AVAILABLE = "available"


def _get_endpoint(request):
    endpoint = getattr(settings, 'SGS_SERVICE_URL', None)
    if not endpoint:
        try:
            endpoint = base.url_for(request, 'sg-service')
            return endpoint
        except exceptions.ServiceCatalogException:
            LOG.debug('No sgs service configured.')
            raise
    return endpoint


def sgsclient(request):
    endpoint = _get_endpoint(request)
    insecure = getattr(settings, 'SGS_SERVICE_INSECURE', True)

    token_id = request.user.token.id
    c = client.Client(1, endpoint=endpoint, token=token_id,
                      insecure=insecure)
    c.client.auth_token = request.user.token.id
    c.client.management_url = endpoint
    return c


# TODO(w) 1.remove the attr that copy from cinder 2.add sg attr 3.use wrapper
class BaseSgAPIResourceWrapper(base.APIResourceWrapper):
    @property
    def name(self):
        # If a volume doesn't have a name, use its id.
        return (getattr(self._apiresource, 'name', None) or
                getattr(self._apiresource, 'display_name', None) or
                getattr(self._apiresource, 'id', None))

    @property
    def description(self):
        return (getattr(self._apiresource, 'description', None) or
                getattr(self._apiresource, 'display_description', None))


class Volume(BaseSgAPIResourceWrapper):
    _attrs = ['id', 'name', 'description', 'size', 'status', 'created_at',
              'volume_type', 'availability_zone', 'imageRef', 'bootable',
              'snapshot_id', 'source_volid', 'attachments', 'tenant_name',
              'consistencygroup_id', 'os-vol-host-attr:host',
              'os-vol-tenant-attr:tenant_id', 'metadata',
              'volume_image_metadata', 'encrypted', 'transfer']

    @property
    def is_bootable(self):
        return self.bootable == 'true'


class VolumeSnapshot(BaseSgAPIResourceWrapper):
    _attrs = ['id', 'name', 'description', 'size', 'status',
              'created_at', 'volume_id',
              'os-extended-snapshot-attributes:project_id',
              'metadata']


class VolumeBackup(BaseSgAPIResourceWrapper):
    _attrs = ['id', 'name', 'description', 'container', 'size', 'status',
              'created_at', 'volume_id', 'availability_zone']
    _volume = None

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, value):
        self._volume = value


class VolumeReplication(BaseSgAPIResourceWrapper):
    _attrs = ['id', 'name', 'description', 'status',
              'created_at', 'master_volume', 'slave_volume']


class VolumeCheckpoint(BaseSgAPIResourceWrapper):
    _attrs = ['id', 'name', 'description', 'status',
              'created_at', 'replication_id']


def update_pagination(entities, page_size, marker, sort_dir):
    has_more_data, has_prev_data = False, False
    if len(entities) > page_size:
        has_more_data = True
        entities.pop()
        if marker is not None:
            has_prev_data = True
    # first page condition when reached via prev back
    elif sort_dir == 'asc' and marker is not None:
        has_more_data = True
    # last page condition
    elif marker is not None:
        has_prev_data = True

    return entities, has_more_data, has_prev_data


@profiler.trace
def volume_backup_create(request, volume_id, name, description):
    backup = sgsclient(request).backups.create(volume_id, name, description)
    return backup


@profiler.trace
def volume_backup_delete(request, backup_id):
    return sgsclient(request).backups.delete(backup_id)


@profiler.trace
def volume_backup_restore(request, backup_id, volume_id):
    return sgsclient(request).backups.restore(backup_id=backup_id,
                                              volume_id=volume_id)


@profiler.trace
def volume_backup_get(request, backup_id):
    backup = sgsclient(request).backups.get(backup_id)
    return backup


def volume_backup_list(request):
    backups, _, __ = volume_backup_list_paged(request, paginate=False)
    return backups


@profiler.trace
def volume_backup_list_paged(request, marker=None, paginate=False,
                             sort_dir="desc"):
    has_more_data = False
    has_prev_data = False
    backups = []

    c_client = sgsclient(request)
    if c_client is None:
        return backups, has_more_data, has_prev_data

    if paginate:
        page_size = utils.get_page_size(request)
        # sort_key and sort_dir deprecated in kilo, use sort
        # if pagination is true, we use a single sort parameter
        # by default, it is "created_at"
        sort = 'created_at:' + sort_dir
        for b in c_client.backups.list(limit=page_size + 1,
                                       marker=marker,
                                       sort=sort):
            backups.append(VolumeBackup(b))

        backups, has_more_data, has_prev_data = update_pagination(
                backups, page_size, marker, sort_dir)
    else:
        for b in c_client.backups.list():
            backups.append(b)

    return backups, has_more_data, has_prev_data


@profiler.trace
def volume_create(request, size=None, snapshot_id=None, checkpoint_id=None,
                  volume_type=None, availability_zone=None,
                  name=None, description=None):
    data = {'name': name,
            'description': description,
            'volume_type': volume_type,
            'snapshot_id': snapshot_id,
            'checkpoint_id': checkpoint_id,
            'availability_zone': availability_zone,
            'size': size}

    volume = sgsclient(request).volumes.create(**data)
    return volume


@profiler.trace
def volume_delete(request, volume_id):
    return sgsclient(request).volumes.delete(volume_id)


@profiler.trace
def volume_enable(request, volume_id, name=None, description=None):
    data = {'name': name,
            'description': description}

    volume = sgsclient(request).volumes.enable(volume_id, **data)
    return volume


@profiler.trace
def volume_disable(request, volume_id):
    return sgsclient(request).volumes.disable(volume_id)


@profiler.trace
def volume_attach(request, volume_id, instance_uuid, mountpoint, mode='rw',
                  host_name=None):
    data = {'mode': mode,
            'host_name': host_name}

    return sgsclient(request).volumes.attach(volume_id, instance_uuid,
                                             mountpoint, **data)


@profiler.trace
def volume_detach(request, volume_id, attachment_uuid=None):
    return sgsclient(request).volumes.detach(volume_id, attachment_uuid)


@profiler.trace
def volume_get(request, volume_id):
    volume_data = sgsclient(request).volumes.get(volume_id)

    for attachment in volume_data.attachments:
        if "server_id" in attachment:
            instance = nova.server_get(request, attachment['server_id'])
            attachment['instance_name'] = instance.name
        else:
            # Nova volume can occasionally send back error'd attachments
            # the lack a server_id property; to work around that we'll
            # give the attached instance a generic name.
            attachment['instance_name'] = _("Unknown instance")

    return volume_data


@profiler.trace
def volume_list_paged(request, search_opts=None, marker=None, paginate=False,
                      sort_dir="desc"):
    """To see all volumes in the cloud as an admin you can pass in a special
    search option: {'all_tenants': 1}
    """
    has_more_data = False
    has_prev_data = False
    volumes = []

    c_client = sgsclient(request)
    if c_client is None:
        return volumes, has_more_data, has_prev_data

    if paginate:
        page_size = utils.get_page_size(request)
        # sort_key and sort_dir deprecated in kilo, use sort
        # if pagination is true, we use a single sort parameter
        # by default, it is "created_at"
        sort = 'created_at:' + sort_dir
        for v in c_client.volumes.list(search_opts=search_opts,
                                       limit=page_size + 1,
                                       marker=marker,
                                       sort=sort):
            volumes.append(v)
        volumes, has_more_data, has_prev_data = update_pagination(
                volumes, page_size, marker, sort_dir)
    else:
        for v in c_client.volumes.list(search_opts=search_opts):
            volumes.append(v)

    return volumes, has_more_data, has_prev_data


def volume_list(request, search_opts=None, marker=None, sort_dir="desc"):
    volumes, _, __ = volume_list_paged(
            request, search_opts=search_opts, marker=marker, paginate=False,
            sort_dir=sort_dir)
    return volumes


@profiler.trace
def volume_update(request, volume_id, name, description):
    vol_data = {'name': name,
                'description': description}
    return sgsclient(request).volumes.update(volume_id,
                                             **vol_data)


@profiler.trace
def volume_snapshot_create(request, volume_id, name=None, description=None):
    data = {'name': name,
            'description': description}

    return sgsclient(request).snapshots.create(
            volume_id, **data)


@profiler.trace
def volume_snapshot_delete(request, snapshot_id):
    return sgsclient(request).snapshots.delete(snapshot_id)


@profiler.trace
def volume_snapshot_update(request, snapshot_id, name, description):
    snapshot_data = {'name': name,
                     'description': description}
    return sgsclient(request).snapshots.update(snapshot_id,
                                               **snapshot_data)


@profiler.trace
def volume_snapshot_get(request, snapshot_id):
    snapshot = sgsclient(request).snapshots.get(snapshot_id)
    return snapshot


@profiler.trace
def volume_snapshot_list(request, search_opts=None):
    snapshots, _, __ = volume_snapshot_list_paged(request,
                                                  search_opts=search_opts,
                                                  paginate=False)
    return snapshots


@profiler.trace
def volume_snapshot_list_paged(request, search_opts=None, marker=None,
                               paginate=False, sort_dir="desc"):
    has_more_data = False
    has_prev_data = False
    snapshots = []
    c_client = sgsclient(request)
    if c_client is None:
        return snapshots, has_more_data, has_more_data

    if paginate:
        page_size = utils.get_page_size(request)
        # sort_key and sort_dir deprecated in kilo, use sort
        # if pagination is true, we use a single sort parameter
        # by default, it is "created_at"
        sort = 'created_at:' + sort_dir
        for s in c_client.snapshots.list(search_opts=search_opts,
                                         limit=page_size + 1,
                                         marker=marker,
                                         sort=sort):
            snapshots.append(s)

        snapshots, has_more_data, has_prev_data = update_pagination(
                snapshots, page_size, marker, sort_dir)
    else:
        for s in c_client.snapshots.list(search_opts=search_opts):
            snapshots.append(s)

    return snapshots, has_more_data, has_prev_data


@profiler.trace
def volume_checkpoint_create(request, replication_id, name=None,
                             description=None):
    data = {'name': name,
            'description': description}

    return sgsclient(request).checkpoints.create(
            replication_id, **data)


@profiler.trace
def volume_checkpoint_delete(request, checkpoint_id):
    return sgsclient(request).checkpoints.delete(checkpoint_id)


@profiler.trace
def volume_checkpoint_update(request, checkpoint_id, name, description):
    checkpoint_data = {'name': name,
                       'description': description}
    return sgsclient(request).checkpoints.update(checkpoint_id,
                                                 **checkpoint_data)


@profiler.trace
def volume_checkpoint_get(request, checkpoint_id):
    checkpoint = sgsclient(request).checkpoints.get(checkpoint_id)
    return checkpoint


@profiler.trace
def volume_checkpoint_list(request, search_opts=None):
    checkpoints, _, __ = volume_checkpoint_list_paged(request,
                                                      search_opts=search_opts,
                                                      paginate=False)
    return checkpoints


@profiler.trace
def volume_checkpoint_list_paged(request, search_opts=None, marker=None,
                                 paginate=False, sort_dir="desc"):
    has_more_data = False
    has_prev_data = False
    checkpoints = []
    c_client = sgsclient(request)
    if c_client is None:
        return checkpoints, has_more_data, has_more_data

    if paginate:
        page_size = utils.get_page_size(request)
        # sort_key and sort_dir deprecated in kilo, use sort
        # if pagination is true, we use a single sort parameter
        # by default, it is "created_at"
        sort = 'created_at:' + sort_dir
        for s in c_client.checkpoints.list(search_opts=search_opts,
                                           limit=page_size + 1,
                                           marker=marker,
                                           sort=sort):
            checkpoints.append(s)

        checkpoints, has_more_data, has_prev_data = update_pagination(
                checkpoints, page_size, marker, sort_dir)
    else:
        for s in c_client.checkpoints.list(search_opts=search_opts):
            checkpoints.append(s)

    return checkpoints, has_more_data, has_prev_data


@profiler.trace
def volume_checkpoint_rollback(request, checkpoint_id):
    return sgsclient(request).checkpoints.rollback(checkpoint_id)


@profiler.trace
def volume_replication_create(request, master_volume, slave_volume,
                              name=None, description=None):
    data = {'name': name,
            'description': description}

    return sgsclient(request).replications.create(master_volume,
                                                  slave_volume, **data)


@profiler.trace
def volume_replication_delete(request, replication_id):
    return sgsclient(request).replications.delete(replication_id)


@profiler.trace
def volume_replication_update(request, replication_id, name, description):
    replication_data = {'name': name,
                        'description': description}
    return sgsclient(request).replications.update(replication_id,
                                                  **replication_data)


@profiler.trace
def volume_replication_get(request, replication_id):
    replication = sgsclient(request).replications.get(replication_id)
    return replication


@profiler.trace
def volume_replication_list(request, search_opts=None):
    replications, _, __ = volume_replication_list_paged(
            request, search_opts=search_opts, paginate=False)
    return replications


@profiler.trace
def volume_replication_list_paged(request, search_opts=None, marker=None,
                                  paginate=False, sort_dir="desc"):
    has_more_data = False
    has_prev_data = False
    replications = []
    c_client = sgsclient(request)
    if c_client is None:
        return replications, has_more_data, has_more_data

    if paginate:
        page_size = utils.get_page_size(request)
        # sort_key and sort_dir deprecated in kilo, use sort
        # if pagination is true, we use a single sort parameter
        # by default, it is "created_at"
        sort = 'created_at:' + sort_dir
        for s in c_client.replications.list(search_opts=search_opts,
                                            limit=page_size + 1,
                                            marker=marker,
                                            sort=sort):
            replications.append(s)

        replications, has_more_data, has_prev_data = update_pagination(
                replications, page_size, marker, sort_dir)
    else:
        for s in c_client.replications.list(search_opts=search_opts):
            replications.append(s)

    return replications, has_more_data, has_prev_data


@profiler.trace
def volume_replication_enable(request, replication_id):
    return sgsclient(request).replications.enable(replication_id)


@profiler.trace
def volume_replication_disable(request, replication_id):
    return sgsclient(request).replications.disable(replication_id)


@profiler.trace
def volume_replication_failover(request, replication_id):
    return sgsclient(request).replications.failover(replication_id)


@profiler.trace
def volume_replication_reverse(request, replication_id):
    return sgsclient(request).replications.reverse(replication_id)
