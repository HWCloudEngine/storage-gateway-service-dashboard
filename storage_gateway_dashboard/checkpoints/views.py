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
from django.core.urlresolvers import reverse_lazy
from django.utils.translation import ugettext_lazy as _

from horizon import exceptions
from horizon import forms
from horizon import tables
from horizon import tabs
from horizon.utils import memoized

from storage_gateway_dashboard.api import api as sg_api
from storage_gateway_dashboard.checkpoints \
    import forms as checkpoint_forms
from storage_gateway_dashboard.checkpoints \
    import tables as checkpoint_tables
from storage_gateway_dashboard.checkpoints \
    import tabs as checkpoint_tabs
from storage_gateway_dashboard.common import table as common_table


class CheckpointsView(tables.DataTableView, common_table.PagedTableMixin):
    table_class = checkpoint_tables.VolumeCheckpointsTable
    page_title = _("Checkpoints")
    template_name = 'common/_data_table_view.html'

    def get_data(self):
        checkpoints = []
        replications = {}
        try:
            marker, sort_dir = self._get_marker()
            checkpoints, self._has_more_data, self._has_prev_data = \
                sg_api.volume_checkpoint_list_paged(
                        self.request, paginate=True, marker=marker,
                        sort_dir=sort_dir)
            replications = sg_api.volume_replication_list(self.request)
            replications = dict((v.id, v) for v in replications)
        except Exception:
            exceptions.handle(self.request, _("Unable to retrieve "
                                              "volume checkpoints."))

        for checkpoint in checkpoints:
            rep = replications.get(checkpoint.replication_id, None)
            setattr(checkpoint, '_replication', rep)

        return checkpoints


class UpdateView(forms.ModalFormView):
    form_class = checkpoint_forms.UpdateForm
    form_id = "update_checkpoint_form"
    template_name = 'checkpoints/update.html'
    submit_label = _("Save Changes")
    submit_url = "horizon:storage-gateway:checkpoints:update"
    success_url = reverse_lazy("horizon:storage-gateway:checkpoints:index")
    page_title = _("Edit Checkpoint")

    @memoized.memoized_method
    def get_object(self):
        checkpoint_id = self.kwargs['checkpoint_id']
        try:
            self._object = sg_api.volume_checkpoint_get(self.request,
                                                        checkpoint_id)
        except Exception:
            msg = _('Unable to retrieve checkpoints.')
            url = reverse('horizon:storage-gateway:checkpoints:index')
            exceptions.handle(self.request, msg, redirect=url)
        return self._object

    def get_context_data(self, **kwargs):
        context = super(UpdateView, self).get_context_data(**kwargs)
        context['checkpoint'] = self.get_object()
        args = (self.kwargs['checkpoint_id'],)
        context['submit_url'] = reverse(self.submit_url, args=args)
        return context

    def get_initial(self):
        checkpoint = self.get_object()
        return {'checkpoint_id': self.kwargs["checkpoint_id"],
                'name': checkpoint.name,
                'description': checkpoint.description}


class DetailView(tabs.TabView):
    tab_group_class = checkpoint_tabs.CheckpointDetailTabs
    template_name = 'horizon/common/_detail.html'
    page_title = "{{ checkpoint.name|default:checkpoint.id }}"
    replication_url = 'horizon:storage-gateway:replications:detail'

    def get_context_data(self, **kwargs):
        context = super(DetailView, self).get_context_data(**kwargs)
        checkpoint = self.get_data()
        checkpoint.replication_url = reverse(self.replication_url,
                                             args=(checkpoint.replication_id,))
        table = checkpoint_tables.VolumeCheckpointsTable(self.request)
        context["checkpoint"] = checkpoint
        context["url"] = self.get_redirect_url()
        context["actions"] = table.render_row_actions(checkpoint)
        return context

    @memoized.memoized_method
    def get_data(self):
        try:
            checkpoint_id = self.kwargs['checkpoint_id']
            checkpoint = sg_api.volume_checkpoint_get(self.request,
                                                      checkpoint_id)
        except Exception:
            redirect = self.get_redirect_url()
            exceptions.handle(self.request,
                              _('Unable to retrieve checkpoint details.'),
                              redirect=redirect)
        return checkpoint

    @staticmethod
    def get_redirect_url():
        return reverse('horizon:storage-gateway:checkpoints:index')

    def get_tabs(self, request, *args, **kwargs):
        checkpoint = self.get_data()
        return self.tab_group_class(request, checkpoint=checkpoint, **kwargs)
