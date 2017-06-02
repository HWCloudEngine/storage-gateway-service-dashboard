# Copyright 2012 Nebula, Inc.
# All rights reserved.

# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""
Views for managing volumes.
"""

from django.core.urlresolvers import reverse
from django.forms import ValidationError
from django.utils.translation import ugettext_lazy as _

from horizon import exceptions
from horizon import forms
from horizon import messages
from horizon.utils.memoized import memoized

from openstack_dashboard import api
from openstack_dashboard.api import cinder
from openstack_dashboard.api import nova
from openstack_dashboard.usage import quotas

from storage_gateway_dashboard.api import api as sg_api
from storage_gateway_dashboard.volumes import tables


# Determine whether the extension for Cinder AZs is enabled
def cinder_az_supported(request):
    try:
        return cinder.extension_supported(request, 'AvailabilityZones')
    except Exception:
        exceptions.handle(request, _('Unable to determine if availability '
                                     'zones extension is supported.'))
        return False


def availability_zones(request):
    zone_list = []
    if cinder_az_supported(request):
        try:
            zones = api.cinder.availability_zone_list(request)
            zone_list = [(zone.zoneName, zone.zoneName)
                         for zone in zones if zone.zoneState['available']]
            zone_list.sort()
        except Exception:
            exceptions.handle(request, _('Unable to retrieve availability '
                                         'zones.'))
    if not zone_list:
        zone_list.insert(0, ("", _("No availability zones found")))
    elif len(zone_list) > 1:
        zone_list.insert(0, ("", _("Any Availability Zone")))

    return zone_list


class CreateForm(forms.SelfHandlingForm):
    name = forms.CharField(max_length=255, label=_("Volume Name"),
                           required=False)
    description = forms.CharField(max_length=255, widget=forms.Textarea(
            attrs={'rows': 4}),
                                  label=_("Description"), required=False)
    volume_source_type = forms.ChoiceField(
            label=_("Volume Source Type"),
            required=False,
            widget=forms.ThemableSelectWidget(attrs={
                'class': 'switchable',
                'data-slug': 'source'}))
    snapshot_source = forms.ChoiceField(
            label=_("Use snapshot as a source"),
            widget=forms.ThemableSelectWidget(
                    attrs={'class': 'snapshot-selector'},
                    data_attrs=('name', 'id'),
                    transform=lambda x: "%s (%s GiB)" % (x.name, x.id)),
            required=False)
    checkpoint_source = forms.ChoiceField(
            label=_("Use checkpoint as a source"),
            widget=forms.ThemableSelectWidget(
                    attrs={'class': 'snapshot-selector'},
                    data_attrs=('name', 'id'),
                    transform=lambda x: "%s (%s GiB)" % (x.name, x.id)),
            required=False)
    type = forms.ChoiceField(
            label=_("Type"),
            required=False,
            widget=forms.ThemableSelectWidget(
                    attrs={'class': 'switched',
                           'data-switch-on': 'source',
                           'data-source-no_source_type': _('Type'),
                           'data-source-image_source': _('Type')}))
    size = forms.IntegerField(min_value=1, initial=1, label=_("Size (GiB)"))
    availability_zone = forms.ChoiceField(
            label=_("Availability Zone"),
            required=False,
            widget=forms.ThemableSelectWidget(
                    attrs={'class': 'switched',
                           'data-switch-on': 'source',
                           'data-source-no_source_type': _(
                                   'Availability Zone'),
                           'data-source-image_source': _(
                                   'Availability Zone')}))

    def prepare_source_fields_if_checkpoint_specified(self, request):
        try:
            checkpoint = self.get_checkpoint(request,
                                             request.GET["checkpoint_id"])
            replication = self.get_replication(request,
                                               checkpoint.replication_id)
            master_volume = self.get_volume(request,
                                            replication.master_volume)
            master_az = master_volume.availability_zone
            slave_volume = self.get_volume(request,
                                           replication.slave_volume)
            slave_az = slave_volume.availability_zone
            self.fields['name'].initial = checkpoint.name
            self.fields['size'].initial = master_volume.size
            self.fields['checkpoint_source'].choices = ((checkpoint.id,
                                                         checkpoint),)
            self.fields['availability_zone'].choices = \
                [(master_az, master_az), (slave_az, slave_az)]
            try:
                # Set the volume type from the original volume
                orig_volume = cinder.volume_get(request,
                                                replication.master_volume)
                self.fields['type'].initial = orig_volume.volume_type
            except Exception:
                pass
            self.fields['size'].help_text = (
                _('Volume size must be equal to or greater than the '
                  'master_volume size (%sGiB)') % master_volume.size)
            del self.fields['volume_source_type']
            del self.fields['snapshot_source']

        except Exception:
            exceptions.handle(request,
                              _('Unable to load the specified snapshot.'))

    def prepare_source_fields_if_snapshot_specified(self, request):
        try:
            snapshot = self.get_snapshot(request,
                                         request.GET["snapshot_id"])
            self.fields['name'].initial = snapshot.name
            self.fields['snapshot_source'].choices = ((snapshot.id,
                                                       snapshot),)
            try:
                # Set the volume type from the original volume
                orig_volume = cinder.volume_get(request,
                                                snapshot.volume_id)
                self.fields['type'].initial = orig_volume.volume_type
                self.fields['size'].initial = orig_volume.size
            except Exception:
                pass
            self.fields['size'].help_text = (
                _('Volume size must be equal to or greater than the '
                  'snapshot size (%sGiB)') % orig_volume.size)
            self.fields['type'].widget = forms.widgets.HiddenInput()
            del self.fields['volume_source_type']
            del self.fields['availability_zone']
            del self.fields['checkpoint_source']

        except Exception:
            exceptions.handle(request,
                              _('Unable to load the specified snapshot.'))

    def prepare_source_fields_default(self, request):
        source_type_choices = []
        self.fields['availability_zone'].choices = \
            availability_zones(request)

        try:
            available = sg_api.VOLUME_STATE_AVAILABLE
            snapshots = sg_api.volume_snapshot_list(
                    request, search_opts=dict(status=available))
            if snapshots:
                source_type_choices.append(("snapshot_source",
                                            _("Snapshot")))
                choices = [('', _("Choose a snapshot"))] + \
                          [(s.id, s) for s in snapshots]
                self.fields['snapshot_source'].choices = choices
            else:
                del self.fields['snapshot_source']
        except Exception:
            exceptions.handle(request,
                              _("Unable to retrieve volume snapshots."))

        try:
            checkpoints = sg_api.volume_checkpoint_list(
                    request, search_opts=dict(status=available))
            if checkpoints:
                source_type_choices.append(("checkpoint_source",
                                            _("Checkpoint")))
                choices = [('', _("Choose a checkpoint"))] + \
                          [(s.id, s) for s in checkpoints]
                self.fields['checkpoint_source'].choices = choices
            else:
                del self.fields['checkpoint_source']
        except Exception:
            exceptions.handle(request,
                              _("Unable to retrieve volume checkpoints."))

        if source_type_choices:
            choices = ([('no_source_type',
                         _("No source, empty volume"))] +
                       source_type_choices)
            self.fields['volume_source_type'].choices = choices
        else:
            del self.fields['volume_source_type']

    def __init__(self, request, *args, **kwargs):
        super(CreateForm, self).__init__(request, *args, **kwargs)
        volume_types = []
        try:
            volume_types = cinder.volume_type_list(request)
        except Exception:
            redirect_url = reverse("horizon:storage-gateway:volumes:index")
            error_message = _('Unable to retrieve the volume type list.')
            exceptions.handle(request, error_message, redirect=redirect_url)
        self.fields['type'].choices = [("", _("No volume type"))] + \
                                      [(type.name, type.name)
                                       for type in volume_types]
        if 'initial' in kwargs and 'type' in kwargs['initial']:
            # if there is a default volume type to select, then remove
            # the first ""No volume type" entry
            self.fields['type'].choices.pop(0)

        if "snapshot_id" in request.GET:
            self.prepare_source_fields_if_snapshot_specified(request)
        elif 'checkpoint_id' in request.GET:
            self.prepare_source_fields_if_checkpoint_specified(request)
        else:
            self.prepare_source_fields_default(request)

    def clean(self):
        cleaned_data = super(CreateForm, self).clean()
        source_type = self.cleaned_data.get('volume_source_type')
        if (source_type == 'checkpoint_source' and
                not cleaned_data.get('checkpoint_source')):
            msg = _('Checkpoint source must be specified')
            self._errors['checkpoint_source'] = self.error_class([msg])
        elif (source_type == 'snapshot_source' and not cleaned_data.get(
                'snapshot_source')):
            msg = _('Snapshot source must be specified')
            self._errors['snapshot_source'] = self.error_class([msg])
        return cleaned_data

    def get_volumes(self, request):
        volumes = []
        try:
            available = sg_api.VOLUME_STATE_ENABLED
            volumes = sg_api.volume_list(self.request,
                                         search_opts=dict(status=available))
        except Exception:
            exceptions.handle(request,
                              _('Unable to retrieve list of volumes.'))
        return volumes

    def handle(self, request, data):
        try:
            usages = quotas.tenant_limit_usages(self.request)
            availableGB = \
                usages['maxTotalVolumeGigabytes'] - usages['gigabytesUsed']
            availableVol = usages['maxTotalVolumes'] - usages['volumesUsed']

            snapshot_id = None
            checkpoint_id = None
            source_type = data.get('volume_source_type', None)
            az = data.get('availability_zone', None) or None
            volume_type = data.get('type')

            if (data.get("snapshot_source", None) and
                    source_type in ['', None, 'snapshot_source']):
                # Create from Snapshot
                snapshot = self.get_snapshot(request,
                                             data["snapshot_source"])
                orig_volume = cinder.volume_get(request,
                                                snapshot.volume_id)
                snapshot_id = snapshot.id
                if data['size'] < orig_volume.size:
                    error_message = (_('The volume size cannot be less than '
                                       'the snapshot size (%sGiB)')
                                     % orig_volume.size)
                    raise ValidationError(error_message)
                az = None
                volume_type = ""
            if (data.get("checkpoint_source", None) and
                    source_type in ['', None, 'checkpoint_source']):
                # Create from Checkpoint
                checkpoint = self.get_checkpoint(request,
                                                 data["snapshot_source"])
                checkpoint_id = checkpoint.id
                check_size = self.fields['size'].initial
                if data['size'] < check_size:
                    error_message = (_('The volume size cannot be less than '
                                       'the master_volume size (%sGiB)')
                                     % check_size)
                    raise ValidationError(error_message)
            else:
                if type(data['size']) is str:
                    data['size'] = int(data['size'])

            if availableGB < data['size']:
                error_message = _('A volume of %(req)iGiB cannot be created '
                                  'as you only have %(avail)iGiB of your '
                                  'quota available.')
                params = {'req': data['size'],
                          'avail': availableGB}
                raise ValidationError(error_message % params)
            elif availableVol <= 0:
                error_message = _('You are already using all of your available'
                                  ' volumes.')
                raise ValidationError(error_message)

            volume = sg_api.volume_create(request,
                                          size=data['size'],
                                          name=data['name'],
                                          description=data['description'],
                                          volume_type=volume_type,
                                          snapshot_id=snapshot_id,
                                          availability_zone=az,
                                          checkpoint_id=checkpoint_id)
            message = _('Creating volume "%s"') % data['name']
            messages.info(request, message)
            return volume
        except ValidationError as e:
            self.api_error(e.messages[0])
            return False
        except Exception:
            redirect = reverse("horizon:storage-gateway:volumes:index")
            exceptions.handle(request,
                              _("Unable to create volume."),
                              redirect=redirect)

    @memoized
    def get_snapshot(self, request, id):
        return sg_api.volume_snapshot_get(request, id)

    @memoized
    def get_volume(self, request, id):
        return sg_api.volume_get(request, id)

    @memoized
    def get_checkpoint(self, request, id):
        return sg_api.volume_checkpoint_get(request, id)

    @memoized
    def get_replication(self, request, id):
        return sg_api.volume_replication_get(request, id)


class AttachForm(forms.SelfHandlingForm):
    instance = forms.ThemableChoiceField(label=_("Attach to Instance"),
                                         help_text=_("Select an instance to "
                                                     "attach to."))

    device = forms.CharField(label=_("Device Name"),
                             widget=forms.TextInput(attrs={'placeholder':
                                                    '/dev/vdc'}),
                             required=False,
                             help_text=_("Actual device name may differ due "
                                         "to hypervisor settings. If not "
                                         "specified, then hypervisor will "
                                         "select a device name."))
    instance_ip = forms.IPField(label=_("Instance Network Address"),
                                initial="",
                                widget=forms.TextInput(attrs={
                                    'class': 'switched',
                                    'data-switch-on': 'source',
                                    'data-source-manual': _("Network Address"),
                                }),
                                help_text=_(
                                        "The current version we need to "
                                        "provider the ip of instance"),
                                version=forms.IPv4 | forms.IPv6)

    def __init__(self, *args, **kwargs):
        super(AttachForm, self).__init__(*args, **kwargs)

        # Hide the device field if the hypervisor doesn't support it.
        if not nova.can_set_mount_point():
            self.fields['device'].widget = forms.widgets.HiddenInput()

        # populate volume_id
        volume = kwargs.get('initial', {}).get("volume", None)
        if volume:
            volume_id = volume.id
        else:
            volume_id = None
        self.fields['volume_id'] = forms.CharField(widget=forms.HiddenInput(),
                                                   initial=volume_id)

        # Populate instance choices
        instance_list = kwargs.get('initial', {}).get('instances', [])
        instances = []
        for instance in instance_list:
            if instance.status in tables.VOLUME_ATTACH_READY_STATES and \
                    not any(instance.id == att["server_id"]
                            for att in volume.attachments):
                instances.append((instance.id, '%s %s' % (instance.name,
                                                          instance.id)))
        if instances:
            instances.insert(0, ("", _("Select an instance")))
        else:
            instances = (("", _("No instances available")),)
        self.fields['instance'].choices = instances

    def handle(self, request, data):
        instance_choices = dict(self.fields['instance'].choices)
        instance_name = instance_choices.get(data['instance'],
                                             _("Unknown instance (None)"))
        # The name of the instance in the choices list has the ID appended to
        # it, so let's slice that off...
        instance_name = instance_name.rsplit(" (")[0]

        # api requires non-empty device name or None
        instance_ip = data.get('instance_ip') or None

        try:
            attach = sg_api.volume_attach(request,
                                          data['volume_id'],
                                          data['instance'],
                                          instance_ip)
            volume = sg_api.volume_get(request, data('volume_id'))
            message = _('Attaching volume %(vol)s to instance '
                        '%(inst)s on %(dev)s.') % {"vol": volume.name,
                                                   "inst": instance_name,
                                                   "dev": attach.device}
            messages.info(request, message)
            return True
        except Exception:
            redirect = reverse("horizon:storage-gateway:volumes:index")
            exceptions.handle(request,
                              _('Unable to attach volume.'),
                              redirect=redirect)


class CreateSnapshotForm(forms.SelfHandlingForm):
    name = forms.CharField(max_length=255, label=_("Snapshot Name"))
    description = forms.CharField(max_length=255,
                                  widget=forms.Textarea(attrs={'rows': 4}),
                                  label=_("Description"),
                                  required=False)

    def __init__(self, request, *args, **kwargs):
        super(CreateSnapshotForm, self).__init__(request, *args, **kwargs)

        # populate volume_id
        volume_id = kwargs.get('initial', {}).get('volume_id', [])
        self.fields['volume_id'] = forms.CharField(widget=forms.HiddenInput(),
                                                   initial=volume_id)

    def handle(self, request, data):
        try:
            volume = sg_api.volume_get(request,
                                       data['volume_id'])
            message = _('Creating volume snapshot "%s".') % data['name']
            if volume.status == 'in-use':
                message = _('Forcing to create snapshot "%s" '
                            'from attached volume.') % data['name']
            snapshot = sg_api.volume_snapshot_create(request,
                                                     data['volume_id'],
                                                     data['name'],
                                                     data['description'])
            messages.info(request, message)
            return snapshot
        except Exception:
            redirect = reverse("horizon:storage-gateway:volumes:index")
            msg = _('Unable to create volume snapshot.')
            exceptions.handle(request,
                              msg,
                              redirect=redirect)


class UpdateForm(forms.SelfHandlingForm):
    name = forms.CharField(max_length=255,
                           label=_("Volume Name"),
                           required=False)
    description = forms.CharField(max_length=255,
                                  widget=forms.Textarea(attrs={'rows': 4}),
                                  label=_("Description"),
                                  required=False)

    def handle(self, request, data):
        volume_id = self.initial['volume_id']
        try:
            sg_api.volume_update(request, volume_id,
                                 name=data['name'],
                                 description=data['description'])
        except Exception:
            redirect = reverse("horizon:storage-gateway:volumes:index")
            exceptions.handle(request,
                              _('Unable to update volume.'),
                              redirect=redirect)

        message = _('Updating volume "%s"') % data['name']
        messages.info(request, message)
        return True


class EnableForm(forms.SelfHandlingForm):
    volume_id = forms.ChoiceField(
            label=_("Select a volume to enable"),
            widget=forms.ThemableSelectWidget(
                    attrs={'class': 'image-selector'},
                    data_attrs=('size', 'name'),
                    transform=lambda x: "%s (%s)" % (
                        x.name, x.id)),
            required=True)
    name = forms.CharField(max_length=255,
                           label=_("Name"), required=False)
    description = forms.CharField(max_length=255,
                                  widget=forms.Textarea(attrs={'rows': 4}),
                                  label=_("Description"),
                                  required=False)

    def __init__(self, request, *args, **kwargs):
        super(EnableForm, self).__init__(request, *args, **kwargs)
        cinder_volumes = self.get_cinder_volumes(request)
        sg_volumes = []
        choices = [('', _("Choose a volume"))]
        for vol in sg_api.volume_list(request):
            sg_volumes.append(vol.id)
        if cinder_volumes:
            choices = [('', _("Choose a volume"))]
            for volume in cinder_volumes:
                if volume.status == "available":
                    choices.append((volume.id, volume))
        self.fields['volume_id'].choices = choices

    def handle(self, request, data):
        try:
            result = None
            volume = cinder.volume_get(request,
                                       data['volume_id'])
            if not volume:
                message = _('Volume not exist,id:"%s".') % data['volume_id']
            else:
                message = _('Enabling volume "%s".') % data['name']
                result = sg_api.volume_enable(request, data['volume_id'],
                                              data['name'],
                                              data['description'])
            messages.info(request, message)
            return result
        except Exception:
            redirect = reverse("horizon:storage-gateway:volumes:index")
            msg = _('Unable to enable volume:%s.') % data['volume_id']
            exceptions.handle(request, msg, redirect=redirect)

    def get_cinder_volumes(self, request):
        volumes = []
        try:
            available = api.cinder.VOLUME_STATE_AVAILABLE
            volumes = cinder.volume_list(self.request,
                                         search_opts=dict(status=available))
        except Exception:
            exceptions.handle(request,
                              _('Unable to retrieve list of volumes.'))
        return volumes
