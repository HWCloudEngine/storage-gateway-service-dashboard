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

from django.core.urlresolvers import reverse
from django.utils import html
from django.utils.http import urlencode
from django.utils import safestring
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import ungettext_lazy

from horizon import tables

from openstack_dashboard import policy

from storage_gateway_dashboard.api import api as sg_api
from storage_gateway_dashboard.volumes \
    import tables as volume_tables


class DeleteVolumeSnapshot(policy.PolicyTargetMixin, tables.DeleteAction):
    help_text = _("Deleted volume snapshots are not recoverable.")

    @staticmethod
    def action_present(count):
        return ungettext_lazy(
                u"Delete Volume Snapshot",
                u"Delete Volume Snapshots",
                count
        )

    @staticmethod
    def action_past(count):
        return ungettext_lazy(
                u"Scheduled deletion of Volume Snapshot",
                u"Scheduled deletion of Volume Snapshots",
                count
        )

    policy_rules = (("volume", "volume:delete_snapshot"),)
    policy_target_attrs = (("project_id",
                            'os-extended-snapshot-attributes:project_id'),)

    def delete(self, request, obj_id):
        sg_api.volume_snapshot_delete(request, obj_id)


class EditVolumeSnapshot(tables.LinkAction):
    name = "edit"
    verbose_name = _("Edit Snapshot")
    url = "horizon:storage-gateway:snapshots:update"
    classes = ("ajax-modal",)
    icon = "pencil"

    def allowed(self, request, snapshot=None):
        return snapshot.status == "available"


class CreateVolumeFromSnapshot(tables.LinkAction):
    name = "create_from_snapshot"
    verbose_name = _("Create Volume")
    url = "horizon:storage-gateway:volumes:create"
    classes = ("ajax-modal",)
    icon = "camera"
    policy_rules = (("volume", "volume:create"),)

    def get_link_url(self, datum):
        base_url = reverse(self.url)
        params = urlencode({"snapshot_id": self.table.get_object_id(datum)})
        return "?".join([base_url, params])

    def allowed(self, request, volume=None):
        if volume:
            return volume.status in ["in-use", "enabled", "available"]
        return False


class UpdateRow(tables.Row):
    ajax = True

    def get_data(self, request, snapshot_id):
        snapshot = None
        try:
            snapshot = sg_api.volume_snapshot_get(request, snapshot_id)
            snapshot._volume = sg_api.volume_get(request, snapshot.volume_id)
        except Exception:
            pass
        return snapshot


class SnapshotVolumeNameColumn(tables.WrappingColumn):
    def get_raw_data(self, snapshot):
        volume = snapshot._volume
        if volume:
            volume_name = volume.name
            volume_name = html.escape(volume_name)
        else:
            volume_name = _("Unknown")
        return safestring.mark_safe(volume_name)

    def get_link_url(self, snapshot):
        volume = snapshot._volume
        if volume:
            volume_id = volume.id
            return reverse(self.link, args=(volume_id,))


class VolumeSnapshotsFilterAction(tables.FilterAction):
    def filter(self, table, snapshots, filter_string):
        """Naive case-insensitive search."""
        query = filter_string.lower()
        return [snapshot for snapshot in snapshots
                if query in snapshot.name.lower()]


class VolumeSnapshotsTable(volume_tables.VolumesTableBase):
    name = tables.WrappingColumn(
            "name",
            verbose_name=_("Name"),
            link="horizon:storage-gateway:snapshots:detail")
    volume_name = SnapshotVolumeNameColumn(
            "name",
            verbose_name=_("Volume Name"),
            link="horizon:storage-gateway:volumes:detail")

    class Meta(object):
        name = "volume_snapshots"
        verbose_name = _("Volume Snapshots")
        pagination_param = 'snapshot_marker'
        prev_pagination_param = 'prev_snapshot_marker'
        table_actions = (VolumeSnapshotsFilterAction, DeleteVolumeSnapshot,)

        row_actions = ((CreateVolumeFromSnapshot,) +
                       (EditVolumeSnapshot, DeleteVolumeSnapshot))
        row_class = UpdateRow
        status_columns = ("status",)
