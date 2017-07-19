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
Views for managing replications.
"""

from django.core.urlresolvers import reverse
from django.forms import ValidationError
from django.utils.translation import ugettext_lazy as _

from horizon import exceptions
from horizon import forms
from horizon import messages
from horizon.utils.memoized import memoized

from storage_gateway_dashboard.api import api as sg_api
from storage_gateway_dashboard.common import fields as common_fields


class CreateForm(forms.SelfHandlingForm):
    name = forms.CharField(max_length=255, label=_("Replication Name"),
                           required=False)
    description = forms.CharField(max_length=255, widget=forms.Textarea(
            attrs={'rows': 4}), label=_("Description"), required=False)
    master_volume = forms.ChoiceField(
            label=_("Master Volume"),
            widget=common_fields.ThemableSelectWidget(
                    attrs={'class': 'image-selector'},
                    data_attrs=('id', 'name'),
                    transform=lambda x: "%s (%s)" % (x.name, x.id)))
    slave_volume = forms.ChoiceField(
            label=_("Slave Volume"),
            widget=common_fields.ThemableSelectWidget(
                    attrs={'class': 'image-selector'},
                    data_attrs=('id', 'name'),
                    transform=lambda x: "%s (%s)" % (x.name, x.id)))

    def prepare_fields_default(self, request):
        try:
            volumes = self.get_volumes(request)
            choices = [(s.id, s) for s in volumes]
            self.fields['master_volume'].choices = choices
            self.fields['slave_volume'].choices = choices
        except Exception:
            exceptions.handle(request,
                              _("Unable to retrieve volumes."))

    def __init__(self, request, *args, **kwargs):
        super(CreateForm, self).__init__(request, *args, **kwargs)
        self.prepare_fields_default(request)

    def clean(self):
        cleaned_data = super(CreateForm, self).clean()
        if not cleaned_data.get('master_volume'):
            msg = _('Replication master_volume must be specified')
            self._errors['master_volume'] = self.error_class([msg])
        if not cleaned_data.get('slave_volume'):
            msg = _('Replication slave_volume must be specified')
            self._errors['slave_volume'] = self.error_class([msg])
        return cleaned_data

    def get_volumes(self, request):
        volumes = []
        try:
            enabled = sg_api.VOLUME_STATE_ENABLED
            for vol in sg_api.volume_list(self.request,
                                          search_opts=dict(status=enabled)):
                if vol.replicate_status in ['deleted', 'disabled', None]:
                    volumes.append(vol)
        except Exception:
            exceptions.handle(request,
                              _('Unable to retrieve list of volumes.'))
        return volumes

    def handle(self, request, data):
        try:
            name = data.get("name", None)
            description = data.get("description", None)
            master_id = data.get('master_volume', None)
            slave_id = data.get('slave_volume', None)
            master_vol = sg_api.volume_get(request, master_id)
            slave_vol = sg_api.volume_get(request, slave_id)

            if master_id == slave_id:
                error_message = (_('The slave volume and master volume can not'
                                   ' be the same'))
                raise ValidationError(error_message)
            if master_vol.availability_zone == slave_vol.availability_zone:
                error_message = (_('The slave volume and master volume can not'
                                   ' be the same availability_zone'))
                raise ValidationError(error_message)

            replication = sg_api.volume_replication_create(
                    request, master_id, slave_id, name, description)
            message = _('Creating replication "%s"') % data['name']
            messages.info(request, message)
            return replication
        except ValidationError as e:
            self.api_error(e.messages[0])
            return False
        except Exception:
            redirect = reverse("horizon:storage-gateway:replications:index")
            exceptions.handle(request,
                              _("Unable to create replication."),
                              redirect=redirect)

    @memoized
    def get_volume(self, request, id):
        return sg_api.volume_get(request, id)


class CreateCheckpointForm(forms.SelfHandlingForm):
    name = forms.CharField(max_length=255, label=_("Checkpoint Name"))
    description = forms.CharField(max_length=255,
                                  widget=forms.Textarea(attrs={'rows': 4}),
                                  label=_("Description"),
                                  required=False)

    def __init__(self, request, *args, **kwargs):
        super(CreateCheckpointForm, self).__init__(request, *args, **kwargs)

        # populate replication_id
        replication_id = kwargs.get('initial', {}).get('replication_id', [])
        self.fields['replication_id'] = forms.CharField(
                widget=forms.HiddenInput(), initial=replication_id)

    def handle(self, request, data):
        try:
            message = _('Creating replication checkpoint "%s".') % data['name']
            checkpoint = sg_api.volume_checkpoint_create(
                    request, data['replication_id'],
                    data['name'], data['description'])
            messages.info(request, message)
            return checkpoint
        except Exception:
            redirect = reverse("horizon:storage-gateway:replications:index")
            msg = _('Unable to create checkpoint.')
            exceptions.handle(request,
                              msg,
                              redirect=redirect)


class RollbackForm(forms.SelfHandlingForm):
    checkpoint = common_fields.ThemableChoiceField(
            label=_("Rollback Replication"),
            help_text=_("Select an checkpoint to rollback."))

    def __init__(self, request, *args, **kwargs):
        super(RollbackForm, self).__init__(request, *args, **kwargs)

        # populate replication_id
        replication_id = kwargs.get('initial', {}).get('replication_id', [])
        self.fields['replication_id'] = forms.CharField(
                widget=forms.HiddenInput(), initial=replication_id)
        # Populate checkpoint choices
        checkpoint_list = kwargs.get('initial', {}).get('checkpoints', [])
        checkpoints = []
        for checkpoint in checkpoint_list:
            if checkpoint.replication_id == replication_id:
                checkpoints.append(
                        (checkpoint.id, '%s (%s)' % (checkpoint.name,
                                                     checkpoint.id)))
        if checkpoints:
            checkpoints.insert(0, ("", _("Select an checkpoint")))
        else:
            checkpoints = (("", _("No checkpoints available")),)
        self.fields['checkpoint'].choices = checkpoints

    def handle(self, request, data):
        try:
            message = _('Rollback replication to checkpoint "%s".') % \
                      data['checkpoint']
            rollback = sg_api.volume_checkpoint_rollback(request,
                                                         data['checkpoint'])
            messages.info(request, message)
            return rollback
        except Exception:
            redirect = reverse("horizon:storage-gateway:replications:index")
            msg = _('Unable to rollback replication.')
            exceptions.handle(request,
                              msg,
                              redirect=redirect)


class UpdateForm(forms.SelfHandlingForm):
    name = forms.CharField(max_length=255,
                           label=_("Replication Name"),
                           required=False)
    description = forms.CharField(max_length=255,
                                  widget=forms.Textarea(attrs={'rows': 4}),
                                  label=_("Description"),
                                  required=False)

    def handle(self, request, data):
        replication_id = self.initial['replication_id']
        try:
            sg_api.volume_replication_update(request, replication_id,
                                             name=data['name'],
                                             description=data['description'])
        except Exception:
            redirect = reverse("horizon:storage-gateway:replications:index")
            exceptions.handle(request,
                              _('Unable to update replication.'),
                              redirect=redirect)

        message = _('Updating replication "%s"') % data['name']
        messages.info(request, message)
        return True
