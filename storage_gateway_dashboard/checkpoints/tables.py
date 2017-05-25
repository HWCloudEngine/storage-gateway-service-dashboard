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

CHECKPOINT_DELETABLE_STATES = ("available", "error")


class DeleteVolumeCheckpoint(policy.PolicyTargetMixin, tables.DeleteAction):
    help_text = _("Deleted checkpoints are not recoverable.")

    @staticmethod
    def action_present(count):
        return ungettext_lazy(
                u"Delete Checkpoint",
                u"Delete Checkpoints",
                count
        )

    @staticmethod
    def action_past(count):
        return ungettext_lazy(
                u"Scheduled deletion of Checkpoint",
                u"Scheduled deletion of Checkpoints",
                count
        )

    def allowed(self, request, checkpoint=None):
        if checkpoint:
            return checkpoint.status in CHECKPOINT_DELETABLE_STATES
        return True

    def delete(self, request, obj_id):
        sg_api.volume_checkpoint_delete(request, obj_id)


class EditVolumeCheckpoint(policy.PolicyTargetMixin, tables.LinkAction):
    name = "edit"
    verbose_name = _("Edit Checkpoint")
    url = "horizon:storage-gateway:checkpoints:update"
    classes = ("ajax-modal",)
    icon = "pencil"

    def allowed(self, request, checkpoint=None):
        return checkpoint.status == "available"


class CreateVolumeFromCheckpoint(tables.LinkAction):
    name = "create_from_checkpoint"
    verbose_name = _("Create Volume")
    url = "horizon:storage-gateway:volumes:create"
    classes = ("ajax-modal",)
    icon = "camera"
    policy_rules = (("volume", "volume:create"),)

    def get_link_url(self, datum):
        base_url = reverse(self.url)
        params = urlencode({"checkpoint_id": self.table.get_object_id(datum)})
        return "?".join([base_url, params])

    def allowed(self, request, checkpoint=None):
        if checkpoint:
            return checkpoint.status in ["available"]
        return False


class UpdateRow(tables.Row):
    ajax = True

    def get_data(self, request, checkpoint_id):
        checkpoint = sg_api.volume_checkpoint_get(request, checkpoint_id)
        checkpoint._replication = sg_api.volume_replication_get(
                request, checkpoint.replication_id)
        return checkpoint


class CheckpointReplicationNameColumn(tables.WrappingColumn):
    def get_raw_data(self, checkpoint):
        replication = checkpoint._replication
        if replication:
            replication_name = replication.name
            replication_name = html.escape(replication_name)
        else:
            replication_name = _("Unknown")
        return safestring.mark_safe(replication_name)

    def get_link_url(self, checkpoint):
        replication = checkpoint._replication
        if replication:
            replication_id = replication.id
            return reverse(self.link, args=(replication_id,))


class VolumeCheckpointsFilterAction(tables.FilterAction):
    def filter(self, table, checkpoints, filter_string):
        """Naive case-insensitive search."""
        query = filter_string.lower()
        return [checkpoint for checkpoint in checkpoints
                if query in checkpoint.name.lower()]


class VolumeCheckpointsTable(volume_tables.VolumesTableBase):
    name = tables.WrappingColumn(
            "name",
            verbose_name=_("Name"),
            link="horizon:storage-gateway:checkpoints:detail")
    replication_name = CheckpointReplicationNameColumn(
            "name",
            verbose_name=_("Replication Name"),
            link="horizon:storage-gateway:replications:detail")

    class Meta(object):
        name = "volume_checkpoints"
        verbose_name = _("Volume Checkpoints")
        pagination_param = 'checkpoint_marker'
        prev_pagination_param = 'prev_checkpoint_marker'
        table_actions = (VolumeCheckpointsFilterAction,
                         DeleteVolumeCheckpoint)

        row_actions = ((CreateVolumeFromCheckpoint,) +
                       (EditVolumeCheckpoint, DeleteVolumeCheckpoint))
        row_class = UpdateRow
        status_columns = ("status",)
