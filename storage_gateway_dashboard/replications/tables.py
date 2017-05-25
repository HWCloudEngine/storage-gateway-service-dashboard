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
from django.http import HttpResponse
from django.utils import html
from django.utils import safestring
from django.utils.translation import npgettext_lazy
from django.utils.translation import pgettext_lazy
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import ungettext_lazy

from horizon import tables
from openstack_dashboard import policy

from storage_gateway_dashboard.api import api as sg_api

REPLICATION_DELETABLE_STATES = ("error", "disabled", 'failed-over')


class DisableReplication(tables.BatchAction):
    name = "disable"
    help_text = _("The data will remain in the volume but storage gateway"
                  " replication will be disabled to the volume")
    action_type = "danger"

    @staticmethod
    def action_present(count):
        return npgettext_lazy(
                "Action to perform (the replication is currently enabled)",
                u"Disable Replication",
                u"Disable Replications",
                count
        )

    # This action is asynchronous.
    @staticmethod
    def action_past(count):
        return npgettext_lazy(
                "Past action (the replication is currently being disabled)",
                u"Disabling Replication",
                u"Disabling Replications",
                count
        )

    def action(self, request, obj_id):
        sg_api.volume_replication_disable(request, obj_id)

    def get_success_url(self, request):
        return reverse('horizon:storage-gateway:replications:index')

    def allowed(self, request, replication):
        if replication:
            return replication.status in ["enabled"]
        return True


class EnableReplication(tables.BatchAction):
    name = "enable"
    classes = ('btn-confirm',)
    help_text = _("storage gateway replication will be enabled to the volume")
    action_type = "danger"

    @staticmethod
    def action_present(count):
        return npgettext_lazy(
                "Action to perform (the replication is currently enabled)",
                u"Enable Replication",
                u"Enable Replications",
                count
        )

    # This action is asynchronous.
    @staticmethod
    def action_past(count):
        return npgettext_lazy(
                "Past action (the replication is currently being enabled)",
                u"Enabling Replication",
                u"Enabling Replications",
                count
        )

    def action(self, request, obj_id):
        sg_api.volume_replication_enable(request, obj_id)

    def get_success_url(self, request):
        return reverse('horizon:storage-gateway:replications:index')

    def allowed(self, request, replication):
        if replication:
            return replication.status in ['disabled']
        return True


class CreateCheckpoint(tables.LinkAction):
    name = "checkpoints"
    verbose_name = _("Create Checkpoint")
    url = "horizon:storage-gateway:replications:create_checkpoint"
    classes = ("ajax-modal",)
    icon = "camera"

    def allowed(self, request, replication=None):
        return replication.status in ("enabled",)


class RollbackReplication(tables.LinkAction):
    name = "rollback"
    verbose_name = _("Rollback Replication")
    url = "horizon:storage-gateway:replications:rollback"
    classes = ("ajax-modal",)
    icon = "camera"

    def allowed(self, request, replication=None):
        if replication and replication.status == 'enabled':
            checkpoints = sg_api.volume_checkpoint_list(request)
            for checkpoint in checkpoints:
                if checkpoint.replication_id == replication.id:
                    return True
        return False


class EditReplication(tables.LinkAction):
    name = "edit"
    verbose_name = _("Edit Replication")
    url = "horizon:storage-gateway:replications:update"
    classes = ("ajax-modal",)
    icon = "pencil"

    def allowed(self, request, replication=None):
        return replication.status in ("disabled", "enabled", 'failed-over')


class UpdateRow(tables.Row):
    ajax = True

    def get_data(self, request, replication_id):
        replication = None
        try:
            replication = sg_api.volume_replication_get(request,
                                                        replication_id)
        except Exception:
            pass
        return replication


class ReplicationsFilterAction(tables.FilterAction):
    def filter(self, table, replications, filter_string):
        """Naive case-insensitive search."""
        q = filter_string.lower()
        return [replication for replication in replications
                if q in replication.name.lower()]


class MasterVolumeNameColumn(tables.Column):
    def get_raw_data(self, replication):
        request = self.table.request
        volume = sg_api.volume_get(request, replication.master_volume)
        if volume:
            volume_name = volume.name
            volume_name = html.escape(volume_name)
        else:
            volume_name = _("Unknown")
        return safestring.mark_safe(volume_name)

    def get_link_url(self, replication):
        request = self.table.request
        volume = sg_api.volume_get(request, replication.master_volume)
        if volume:
            volume_id = volume.id
            return reverse(self.link, args=(volume_id,))


class SlaveVolumeNameColumn(tables.Column):
    def get_raw_data(self, replication):
        request = self.table.request
        volume = sg_api.volume_get(request, replication.slave_volume)
        if volume:
            volume_name = volume.name
            volume_name = html.escape(volume_name)
        else:
            volume_name = _("Unknown")
        return safestring.mark_safe(volume_name)

    def get_link_url(self, replication):
        request = self.table.request
        volume = sg_api.volume_get(request, replication.slave_volume)
        if volume:
            volume_id = volume.id
            return reverse(self.link, args=(volume_id,))


class CreateReplication(tables.LinkAction):
    name = "replications"
    verbose_name = _("Create Replication")
    url = "horizon:storage-gateway:replications:create"
    classes = ("ajax-modal",)

    def allowed(self, request, replication=None):
        return True

    def single(self, table, request, object_id=None):
        self.allowed(request, None)
        return HttpResponse(self.render(is_table_action=True))


class DeleteReplication(policy.PolicyTargetMixin, tables.DeleteAction):
    help_text = _("Deleted volume replications are not recoverable.")

    @staticmethod
    def action_present(count):
        return ungettext_lazy(
                u"Delete Replication",
                u"Delete Replications",
                count
        )

    @staticmethod
    def action_past(count):
        return ungettext_lazy(
                u"Scheduled deletion of Replication",
                u"Scheduled deletion of Replications",
                count
        )

    def allowed(self, request, replication=None):
        if replication:
            return replication.status in REPLICATION_DELETABLE_STATES
        return True

    def delete(self, request, obj_id):
        sg_api.volume_replication_delete(request, obj_id)


class FailoverReplication(tables.BatchAction):
    name = "failover"
    classes = ('btn-confirm',)
    help_text = _("storage gateway replication failover")
    action_type = "danger"

    @staticmethod
    def action_present(count):
        return npgettext_lazy(
                "Action to perform (the replication is currently enabled)",
                u"Failover Replication",
                u"Failover Replications",
                count
        )

    # This action is asynchronous.
    @staticmethod
    def action_past(count):
        return npgettext_lazy(
                "Past action (the replication is currently being failover)",
                u"Failover Replication",
                u"Failover Replications",
                count
        )

    def action(self, request, obj_id):
        sg_api.volume_replication_failover(request, obj_id)

    def get_success_url(self, request):
        return reverse('horizon:storage-gateway:replications:index')

    def allowed(self, request, replication):
        if replication:
            return replication.status in ["enabled"]
        return True


class ReverseReplication(tables.BatchAction):
    name = "reverse"
    classes = ('btn-confirm',)
    help_text = _("storage gateway replication reverse")
    action_type = "danger"

    @staticmethod
    def action_present(count):
        return npgettext_lazy(
                "Action to perform (the replication is currently enabled)",
                u"Reverse Replication",
                u"Reverse Replications",
                count
        )

    # This action is asynchronous.
    @staticmethod
    def action_past(count):
        return npgettext_lazy(
                "Past action (the replication is currently being reverse)",
                u"Reverse Replication",
                u"Reverse Replications",
                count
        )

    def action(self, request, obj_id):
        sg_api.volume_replication_reverse(request, obj_id)

    def get_success_url(self, request):
        return reverse('horizon:storage-gateway:replications:index')

    def allowed(self, request, replication):
        if replication:
            return replication.status in ["failed-over"]
        return True


class VolumeReplicationsTable(tables.DataTable):
    STATUS_CHOICES = (
        ("creating", None),
        ("error", False),
        ('enabling', None),
        ('failing-over', None),
        ('reversing', None),
        ('rolling-back', None),
        ('enabled', True),
        ('disabled', True),
        ('failed-over', True),
        ('deleted', True),
        (None, True),
    )
    STATUS_DISPLAY_CHOICES = (
        ("error", pgettext_lazy("Current status of a Replication", u"Error")),
        ("creating", pgettext_lazy("Current status of a Replication",
                                   u"Creating")),
        ("deleting", pgettext_lazy("Current status of a Replication",
                                   u"Deleting")),
        ("error_deleting", pgettext_lazy("Current status of a Replication",
                                         u"Error deleting")),
        ("enabling", pgettext_lazy("Current status of a Replication",
                                   u"Enabling")),
        ("enabled", pgettext_lazy("Current status of a Replication",
                                  u"Enabled")),
        ("disabling", pgettext_lazy("Current status of a Replication",
                                    u"Disabling")),
        ("disabled", pgettext_lazy("Current status of a Replication",
                                   u"Disabled")),
        ("failing-over", pgettext_lazy("Current status of a Replication",
                                       u"Failing-over")),
        ("failed-over", pgettext_lazy("Current status of a Replication",
                                      u"Failed-over")),
        ("reversing", pgettext_lazy("Current status of a Replication",
                                    u"Reversing")),
        ("deleted", pgettext_lazy("Current status of a Replication",
                                  u"Deleted")),
        ("rolling-back", pgettext_lazy("Current status of a Volume",
                                       u"Rolling-back")),
    )
    name = tables.WrappingColumn(
            "name", verbose_name=_("Name"),
            link="horizon:storage-gateway:replications:detail")
    description = tables.Column("description",
                                verbose_name=_("Description"),
                                truncate=40)
    status = tables.Column("status",
                           verbose_name=_("Status"),
                           status=True,
                           status_choices=STATUS_CHOICES,
                           display_choices=STATUS_DISPLAY_CHOICES)
    master_volume = MasterVolumeNameColumn(
            "master_volume", verbose_name=_("Master Volume"),
            link="horizon:storage-gateway:volumes:detail")
    slave_volume = SlaveVolumeNameColumn(
            "slave_volume", verbose_name=_("Slave Volume"),
            link="horizon:storage-gateway:volumes:detail")

    class Meta(object):
        name = "replications"
        verbose_name = _("Storage Gateway Replications")
        status_columns = ["status"]
        row_class = UpdateRow
        table_actions = (CreateReplication, DeleteReplication,
                         ReplicationsFilterAction)
        row_actions = ((EditReplication, DisableReplication,
                        EnableReplication, RollbackReplication) +
                       (CreateCheckpoint, FailoverReplication,
                        ReverseReplication))
