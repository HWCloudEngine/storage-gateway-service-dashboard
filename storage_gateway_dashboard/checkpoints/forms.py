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


from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _

from horizon import exceptions
from horizon import forms
from horizon import messages

from storage_gateway_dashboard.api import api as sg_api


class UpdateForm(forms.SelfHandlingForm):
    name = forms.CharField(max_length=255, label=_("Checkpoint Name"))
    description = forms.CharField(max_length=255,
                                  widget=forms.Textarea(attrs={'rows': 4}),
                                  label=_("Description"),
                                  required=False)

    def handle(self, request, data):
        checkpoint_id = self.initial['checkpoint_id']
        try:
            sg_api.volume_checkpoint_update(request,
                                            checkpoint_id,
                                            data['name'],
                                            data['description'])

            message = _('Updating volume checkpoint "%s"') % data['name']
            messages.info(request, message)
            return True
        except Exception:
            redirect = reverse("horizon:storage-gateway:checkpoints:index")
            exceptions.handle(request,
                              _('Unable to update checkpoint.'),
                              redirect=redirect)
