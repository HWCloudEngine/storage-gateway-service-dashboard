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
from django.utils.translation import ugettext_lazy as _

from horizon import exceptions
from horizon import tabs

from storage_gateway_dashboard.api import api as sg_api


class OverviewTab(tabs.Tab):
    name = _("Overview")
    slug = "overview"
    template_name = ("checkpoints/_detail_overview.html")

    def get_context_data(self, request):
        try:
            checkpoint = self.tab_group.kwargs['checkpoint']
            replication = sg_api.volume_replication_get(
                    request, checkpoint.replication_id)
        except Exception:
            redirect = self.get_redirect_url()
            exceptions.handle(self.request,
                              _('Unable to retrieve checkpoint details.'),
                              redirect=redirect)
        return {"checkpoint": checkpoint,
                "replication": replication}

    def get_redirect_url(self):
        return reverse('horizon:storage-gateway:checkpoints:index')


class CheckpointDetailTabs(tabs.TabGroup):
    slug = "checkpoint_details"
    tabs = (OverviewTab,)
