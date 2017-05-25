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

"""
Views for managing replications.
"""


from django.core.urlresolvers import reverse
from django.core.urlresolvers import reverse_lazy
from django.utils.translation import ugettext_lazy as _

from horizon import exceptions
from horizon import forms
from horizon import tables
from horizon import tabs
from horizon.utils import memoized

from openstack_dashboard.utils import filters

from storage_gateway_dashboard.api import api as sg_api
from storage_gateway_dashboard.common import table as common_table
from storage_gateway_dashboard.replications \
    import forms as rep_forms
from storage_gateway_dashboard.replications \
    import tables as rep_tables
from storage_gateway_dashboard.replications \
    import tabs as rep_tabs


class ReplicationsView(common_table.PagedTableMixin, tables.DataTableView):
    table_class = rep_tables.VolumeReplicationsTable
    page_title = _("Storage Gateway Replications")

    def get_data(self):
        replications = []
        volumes = {}
        try:
            marker, sort_dir = self._get_marker()
            replications, self._has_more_data, self._has_prev_data = \
                sg_api.volume_replication_list_paged(self.request,
                                                     paginate=True,
                                                     marker=marker,
                                                     sort_dir=sort_dir)
            volumes = sg_api.volume_list(self.request)
            volumes = dict((v.id, v) for v in volumes)
        except Exception:
            exceptions.handle(self.request, _("Unable to retrieve "
                                              "volume replications."))

        for replication in replications:
            master_vol = volumes.get(replication.master_volume, None)
            setattr(replication, '_master', master_vol)
            slave_vol = volumes.get(replication.slave_volume, None)
            setattr(replication, '_slave', slave_vol)

        return replications


class DetailView(tabs.TabView):
    tab_group_class = rep_tabs.ReplicationDetailTabs
    template_name = 'horizon/common/_detail.html'
    page_title = "{{ replication.name|default:replication.id }}"

    def get_context_data(self, **kwargs):
        context = super(DetailView, self).get_context_data(**kwargs)
        replication = self.get_data()
        table = rep_tables.VolumeReplicationsTable(self.request)
        context["replication"] = replication
        context["url"] = self.get_redirect_url()
        context["actions"] = table.render_row_actions(replication)
        choices = rep_tables.VolumeReplicationsTable.STATUS_DISPLAY_CHOICES
        replication.status_label = filters.get_display_label(
                choices, replication.status)
        return context

    @memoized.memoized_method
    def get_data(self):
        try:
            replication_id = self.kwargs['replication_id']
            replication = sg_api.volume_replication_get(
                    self.request, replication_id)
        except Exception:
            redirect = self.get_redirect_url()
            exceptions.handle(self.request,
                              _('Unable to retrieve replication details.'),
                              redirect=redirect)
        return replication

    def get_redirect_url(self):
        return reverse('horizon:storage-gateway:replications:index')

    def get_tabs(self, request, *args, **kwargs):
        replication = self.get_data()
        return self.tab_group_class(
                request, replication=replication, **kwargs)


class CreateCheckpointView(forms.ModalFormView):
    form_class = rep_forms.CreateCheckpointForm
    template_name = 'replications/create_checkpoint.html'
    submit_url = "horizon:storage-gateway:replications:create_checkpoint"
    success_url = reverse_lazy('horizon:storage-gateway:replications:index')
    page_title = _("Create Checkpoint")

    def get_context_data(self, **kwargs):
        context = super(CreateCheckpointView, self).get_context_data(**kwargs)
        context['replication_id'] = self.kwargs['replication_id']
        args = (self.kwargs['replication_id'],)
        context['submit_url'] = reverse(self.submit_url, args=args)
        return context

    def get_initial(self):
        return {'replication_id': self.kwargs["replication_id"]}


class CreateReplication(forms.ModalFormView):
    form_class = rep_forms.CreateForm
    template_name = 'replications/create.html'
    submit_label = _("Create Replications")
    submit_url = reverse_lazy("horizon:storage-gateway:replications:create")
    success_url = reverse_lazy('horizon:storage-gateway:replications:index')
    page_title = _("Create Replications")

    def get_initial(self):
        initial = super(CreateReplication, self).get_initial()
        return initial

    def get_context_data(self, **kwargs):
        context = super(CreateReplication, self).get_context_data(**kwargs)
        return context


class RollbackReplication(forms.ModalFormView):
    form_class = rep_forms.RollbackForm
    template_name = 'replications/rollback.html'
    submit_url = "horizon:storage-gateway:replications:rollback"
    success_url = reverse_lazy('horizon:storage-gateway:replications:index')
    page_title = _("Rollback Replication")

    def get_context_data(self, **kwargs):
        context = super(RollbackReplication, self).get_context_data(**kwargs)
        context['replication_id'] = self.kwargs['replication_id']
        args = (self.kwargs['replication_id'],)
        context['submit_url'] = reverse(self.submit_url, args=args)
        return context

    def get_initial(self):
        checkpoints = self._get_checkpoints()
        return {'replication_id': self.kwargs["replication_id"],
                'checkpoints': checkpoints}

    def _get_checkpoints(self):
        try:
            checkpoints = sg_api.volume_checkpoint_list(self.request)
        except Exception:
            redirect = self.get_redirect_url()
            exceptions.handle(self.request,
                              _('Unable to retrieve checkpoints.'),
                              redirect=redirect)
        return checkpoints


class UpdateView(forms.ModalFormView):
    form_class = rep_forms.UpdateForm
    modal_id = "update_replication_modal"
    template_name = 'replications/update.html'
    submit_url = "horizon:storage-gateway:replications:update"
    success_url = reverse_lazy("horizon:storage-gateway:replications:index")
    page_title = _("Edit Replication")

    def get_object(self):
        if not hasattr(self, "_object"):
            replication_id = self.kwargs['replication_id']
            try:
                self._object = sg_api.volume_replication_get(self.request,
                                                             replication_id)
            except Exception:
                msg = _('Unable to retrieve replication.')
                url = reverse('horizon:storage-gateway:replications:index')
                exceptions.handle(self.request, msg, redirect=url)
        return self._object

    def get_context_data(self, **kwargs):
        context = super(UpdateView, self).get_context_data(**kwargs)
        context['replication'] = self.get_object()
        args = (self.kwargs['replication_id'],)
        context['submit_url'] = reverse(self.submit_url, args=args)
        return context

    def get_initial(self):
        replication = self.get_object()
        return {'replication_id': self.kwargs["replication_id"],
                'name': replication.name,
                'description': replication.description}
