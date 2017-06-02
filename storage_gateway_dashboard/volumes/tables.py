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

from django.core.urlresolvers import NoReverseMatch
from django.core.urlresolvers import reverse
from django.http import HttpResponse
from django.utils import html
from django.utils import safestring
from django.utils.translation import npgettext_lazy
from django.utils.translation import pgettext_lazy
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import ungettext_lazy

from horizon import exceptions
from horizon import tables

from openstack_dashboard import api
from openstack_dashboard import policy

from storage_gateway_dashboard.api import api as sg_api
from storage_gateway_dashboard.replications.tables import \
    VolumeReplicationsTable as ReplicationsTable


DISABLE_STATES = ("enabled",)
REP_DISABLE_STATES = ('deleted', 'disabled', None)
DELETABLE_STATES = ("available", "error")
ENABLE_STATES = ("available",)
VOLUME_ATTACH_READY_STATES = ("ACTIVE", "SHUTOFF")


class VolumePolicyTargetMixin(policy.PolicyTargetMixin):
    policy_target_attrs = (("project_id", 'os-vol-tenant-attr:tenant_id'),)


class DisableVolume(tables.DeleteAction):
    help_text = _("Disabled volumes can enable again. "
                  "All data stored in the volume will be remain.")

    @staticmethod
    def action_present(count):
        return ungettext_lazy(
            u"Disable Volume",
            u"Disable Volumes",
            count
        )

    @staticmethod
    def action_past(count):
        return ungettext_lazy(
            u"Scheduled disable of Volume",
            u"Scheduled disable of Volumes",
            count
        )

    def delete(self, request, obj_id):
        sg_api.volume_disable(request, obj_id)

    def allowed(self, request, volume=None):
        if volume:
            return volume.status in DISABLE_STATES and \
                            volume.replicate_status in REP_DISABLE_STATES
        return True


class DeleteVolume(tables.BatchAction):
    name = "delete storage gateway volume"
    classes = ('btn-confirm',)
    help_text = _("Volume will be deleted from storage gateway. ")
    action_type = "danger"

    @staticmethod
    def action_present(count):
        return npgettext_lazy(
                "Action to perform (the volume is currently deleted)",
                u"Delete Volume",
                u"Delete Volumes",
                count
        )

    # This action is asynchronous.
    @staticmethod
    def action_past(count):
        return npgettext_lazy(
                "Past action (the volume is currently being deleted)",
                u"Deleting Volume",
                u"Deleting Volumes",
                count
        )

    def action(self, request, obj_id):
        sg_api.volume_delete(request, obj_id)

    def get_success_url(self, request):
        return reverse('horizon:storage-gateway:volumes:index')

    def allowed(self, request, volume):
        if volume:
            return volume.status in DELETABLE_STATES
        return True


class EnableVolume(tables.LinkAction):
    name = "enable"
    verbose_name = _("Enable Volume")
    url = "horizon:storage-gateway:volumes:enable"
    classes = ("ajax-modal", "btn-create")
    icon = "plus"
    ajax = True

    def __init__(self, attrs=None, **kwargs):
        kwargs['preempt'] = True
        super(EnableVolume, self).__init__(attrs, **kwargs)

    def allowed(self, request, volume=None):
        if volume:
            return volume.status in ("available", "disabled")
        return True

    def single(self, table, request, object_id=None):
        self.allowed(request, None)
        return HttpResponse(self.render(is_table_action=True))


class EditAttachments(tables.LinkAction):
    name = "attachments"
    verbose_name = _("Manage Attachments")
    url = "horizon:storage-gateway:volumes:attach"
    classes = ("ajax-modal",)
    icon = "pencil"

    def allowed(self, request, volume=None):
        if not api.base.is_service_enabled(request, 'compute'):
            return False

        if volume:
            project_id = getattr(volume, "os-vol-tenant-attr:tenant_id", None)
            attach_allowed = \
                policy.check((("compute",
                             "os_compute_api:servers:attach_volume"),),
                             request,
                             {"project_id": project_id})
            detach_allowed = \
                policy.check((("compute",
                             "os_compute_api:servers:detach_volume"),),
                             request,
                             {"project_id": project_id})

            if attach_allowed or detach_allowed:
                return volume.status in ("in-use", "enabled")
        return False


class CreateSnapshot(tables.LinkAction):
    name = "snapshots"
    verbose_name = _("Create Snapshot")
    url = "horizon:storage-gateway:volumes:create_snapshot"
    classes = ("ajax-modal",)
    icon = "camera"

    def allowed(self, request, volume=None):
        return volume.status in ("enabled", 'in-use')


class EditVolume(VolumePolicyTargetMixin, tables.LinkAction):
    name = "edit"
    verbose_name = _("Edit Volume")
    url = "horizon:storage-gateway:volumes:update"
    classes = ("ajax-modal",)
    icon = "pencil"
    policy_rules = (("volume", "volume:update"),)

    def allowed(self, request, volume=None):
        return volume.status in ("available", "in-use", "enabled", 'disabled')


class UpdateRow(tables.Row):
    ajax = True

    def get_data(self, request, volume_id):
        volume = None
        try:
            volume = sg_api.volume_get(request, volume_id)
        except Exception:
            pass
        return volume


def get_size(volume):
    return _("%sGiB") % volume.size


def get_attachment_name(request, attachment):
    server_id = attachment.get("server_id", None)
    if "instance" in attachment and attachment['instance']:
        name = attachment["instance"].name
    else:
        try:
            server = api.nova.server_get(request, server_id)
            name = server.name
        except Exception:
            name = None
            exceptions.handle(request, _("Unable to retrieve "
                                         "attachment information."))
    try:
        url = reverse("horizon:storage-gateway:instances:detail",
                      args=(server_id,))
        instance = '<a href="%s">%s</a>' % (url, html.escape(name))
    except NoReverseMatch:
        instance = html.escape(name)
    return instance


class AttachmentColumn(tables.WrappingColumn):
    """Customized column class.

    So it that does complex processing on the attachments
    for a volume instance.
    """
    def get_raw_data(self, volume):
        request = self.table.request
        link = _('%(dev)s on %(instance)s')
        attachments = []
        # Filter out "empty" attachments which the client returns...
        for attachment in [att for att in volume.attachments if att]:
            # When a volume is attached it may return the server_id
            # without the server name...
            instance = get_attachment_name(request, attachment)
            vals = {"instance": instance,
                    "dev": html.escape(attachment.get("device", ""))}
            attachments.append(link % vals)
        return safestring.mark_safe(", ".join(attachments))


def get_volume_type(volume):
    return volume.volume_type if volume.volume_type != "None" else None


class VolumesTableBase(tables.DataTable):
    STATUS_CHOICES = (
        ("in-use", True),
        ("available", True),
        ("creating", None),
        ("error", False),
        ('enabling', None),
        ('enabled', True),
        ('disabled', True)
    )
    STATUS_DISPLAY_CHOICES = (
        ("available", pgettext_lazy("Current status of a Volume",
                                    u"Available")),
        ("in-use", pgettext_lazy("Current status of a Volume", u"In-use")),
        ("error", pgettext_lazy("Current status of a Volume", u"Error")),
        ("creating", pgettext_lazy("Current status of a Volume",
                                   u"Creating")),
        ("attaching", pgettext_lazy("Current status of a Volume",
                                    u"Attaching")),
        ("detaching", pgettext_lazy("Current status of a Volume",
                                    u"Detaching")),
        ("deleting", pgettext_lazy("Current status of a Volume",
                                   u"Deleting")),
        ("error_deleting", pgettext_lazy("Current status of a Volume",
                                         u"Error deleting")),
        ("backing-up", pgettext_lazy("Current status of a Volume",
                                     u"Backing Up")),
        ("restoring-backup", pgettext_lazy("Current status of a Volume",
                                           u"Restoring Backup")),
        ("error_restoring", pgettext_lazy("Current status of a Volume",
                                          u"Error Restoring")),
        ("enabling", pgettext_lazy("Current status of a Volume", u"Enabling")),
        ("enabled", pgettext_lazy("Current status of a Volume", u"Enabled")),
        ("disabled", pgettext_lazy("Current status of a Volume", u"Disabled")),
        ("rolling-back", pgettext_lazy("Current status of a Volume",
                                       u"Rolling-back")),
    )
    name = tables.Column("name",
                         verbose_name=_("Name"),
                         link="horizon:storage-gateway:volumes:detail")
    description = tables.Column("description",
                                verbose_name=_("Description"),
                                truncate=40)
    status = tables.Column("status",
                           verbose_name=_("Status"),
                           status=True,
                           status_choices=STATUS_CHOICES,
                           display_choices=STATUS_DISPLAY_CHOICES)

    def get_object_display(self, obj):
        return obj.name


class VolumesFilterAction(tables.FilterAction):

    def filter(self, table, volumes, filter_string):
        """Naive case-insensitive search."""
        q = filter_string.lower()
        return [volume for volume in volumes
                if q in volume.name.lower()]


class CreateBackup(tables.LinkAction):
    name = "backups"
    verbose_name = _("Create Backup")
    url = "horizon:storage-gateway:volumes:create_backup"
    classes = ("ajax-modal",)

    def allowed(self, request, volume=None):
        if volume:
            return volume.status in ("enabled", 'in-use')
        return True


class VolumesTable(VolumesTableBase):
    name = tables.WrappingColumn("name",
                                 verbose_name=_("Name"),
                                 link="horizon:storage-gateway:volumes:detail")
    size = tables.Column(get_size,
                         verbose_name=_("Size"),
                         attrs={'data-type': 'size'})
    attachments = AttachmentColumn("attachments",
                                   verbose_name=_("Attached To"))
    availability_zone = tables.Column("availability_zone",
                                      verbose_name=_("Availability Zone"))
    replicate_status = tables.Column(
            "replicate_status",
            verbose_name=_(" Replicate Status"),
            status=True,
            status_choices=ReplicationsTable.STATUS_CHOICES,
            display_choices=ReplicationsTable.STATUS_DISPLAY_CHOICES)

    class Meta(object):
        name = "volumes"
        verbose_name = _("Storage Gateway Volumes")
        status_columns = ["status", "replicate_status"]
        row_class = UpdateRow
        table_actions = (EnableVolume, DisableVolume,
                         VolumesFilterAction)
        row_actions = ((EditVolume,) +
                       (EditAttachments, CreateSnapshot, CreateBackup,
                        DisableVolume, DeleteVolume))


class DetachVolume(tables.BatchAction):
    name = "detach"
    classes = ('btn-detach',)
    policy_rules = (("compute", "os_compute_api:servers:detach_volume"),)
    help_text = _("The data will remain in the volume and another instance"
                  " will be able to access the data if you attach"
                  " this volume to it.")
    action_type = "danger"

    @staticmethod
    def action_present(count):
        return npgettext_lazy(
            "Action to perform (the volume is currently attached)",
            u"Detach Volume",
            u"Detach Volumes",
            count
        )

    # This action is asynchronous.
    @staticmethod
    def action_past(count):
        return npgettext_lazy(
            "Past action (the volume is currently being detached)",
            u"Detaching Volume",
            u"Detaching Volumes",
            count
        )

    def action(self, request, obj_id):
        attachment = self.table.get_object_by_id(obj_id)
        sg_api.volume_detach(request, attachment.get('volume_id', None),
                             attachment.get('server_id', None))

    def get_success_url(self, request):
        return reverse('horizon:storage-gateway:volumes:index')


class AttachedInstanceColumn(tables.WrappingColumn):
    """Customized column class that does complex processing on the attachments
    for a volume instance.
    """

    def get_raw_data(self, attachment):
        request = self.table.request
        return safestring.mark_safe(get_attachment_name(request, attachment))


class AttachmentsTable(tables.DataTable):
    instance = AttachedInstanceColumn(get_attachment_name,
                                      verbose_name=_("Instance"))
    device = tables.Column("device",
                           verbose_name=_("Device"))

    def get_object_id(self, obj):
        return obj['id']

    def get_object_display(self, attachment):
        instance_name = get_attachment_name(self.request, attachment)
        vals = {"volume_name": attachment['volume_name'],
                "instance_name": html.strip_tags(instance_name)}
        return _("Volume %(volume_name)s on instance %(instance_name)s") % vals

    def get_object_by_id(self, obj_id):
        for obj in self.data:
            if self.get_object_id(obj) == obj_id:
                return obj
        raise ValueError('No match found for the id "%s".' % obj_id)

    class Meta(object):
        name = "attachments"
        verbose_name = _("Attachments")
        table_actions = (DetachVolume,)
        row_actions = (DetachVolume,)
