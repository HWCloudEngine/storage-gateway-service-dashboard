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

import itertools

from django.forms import fields
from django.template import Context  # noqa
from django.template.loader import get_template  # noqa
from horizon.forms.fields import SelectWidget  # noqa


class ThemableSelectWidget(SelectWidget):
    """Bootstrap base select field widget."""
    def render(self, name, value, attrs=None, choices=()):
        # NOTE(woodnt): Currently the "attrs" contents are being added to the
        #               select that's hidden.  It's unclear whether this is the
        #               desired behavior.  In some cases, the attribute should
        #               remain solely on the now-hidden select.  But in others
        #               if it should live on the bootstrap button (visible)
        #               or both.

        new_choices = []
        initial_value = value
        for opt_value, opt_label in itertools.chain(self.choices, choices):
            other_html = self.transform_option_html_attrs(opt_label)

            data_attr_html = self.get_data_attrs(opt_label)
            if data_attr_html:
                other_html += ' ' + data_attr_html

            opt_label = self.transform_option_label(opt_label)

            # If value exists, save off its label for use
            if opt_value == value:
                initial_value = opt_label

            if other_html:
                new_choices.append((opt_value, opt_label, other_html))
            else:
                new_choices.append((opt_value, opt_label))

        if value is None and new_choices:
            initial_value = new_choices[0][1]

        attrs = self.build_attrs(attrs)
        id = attrs.pop('id', 'id_%s' % name)

        template = get_template('horizon/common/fields/_themable_select.html')
        context = Context({
            'name': name,
            'options': new_choices,
            'id': id,
            'value': value,
            'initial_value': initial_value,
            'select_attrs': attrs,
        })
        return template.render(context)


class ThemableChoiceField(fields.ChoiceField):
    """Bootstrap based select field."""
    widget = ThemableSelectWidget
