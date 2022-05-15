# -*- coding: utf-8 -*-
#
# This file is part of Glances.
#
# Copyright (C) 2022 Nicolargo <nicolas@nicolargo.com>
#
# Glances is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Glances is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

"""Swap memory plugin."""

from glances.globals import iterkeys
from glances.timer import getTimeSinceLastUpdate
from glances.plugins.plugin.model import GlancesPluginModel
from glances.logger import logger

import psutil

# Fields description
fields_description = {
    'total': {
        'description': 'Total swap memory.',
        'unit': 'bytes',
        'min_symbol': 'K',
        'short_description': 'Total'
    },
    'used': {
        'description': 'Used swap memory.',
        'unit': 'bytes',
        'min_symbol': 'K',
        'short_description': 'Used'
    },
    'free': {
        'description': 'Free swap memory.',
        'unit': 'bytes', 'min_symbol': 'K',
        'short_description': 'Free'
    },
    'percent': {
        'description': 'Used swap memory in percentage.',
        'unit': 'percent'
    },
    'sin': {
        'description': 'The number of bytes the system has swapped in from disk (cumulative).',
        'unit': 'bytes',
        'min_symbol': 'K',
    },
    'sout': {
        'description': 'The number of bytes the system has swapped out from disk (cumulative).',
        'unit': 'bytes',
        'min_symbol': 'K',
    },
    'time_since_update': {'description': 'Number of seconds since last update.', 'unit': 'seconds'},
    # 'trend': 'percent'
}

# Define the template (for the Rich interface)
template = {
    'title': '[blue]Swap[/] {percent}%',
    # content_row is defined, so the row list will be:
    'content_row': ['total', 'used', 'free'],
    'content_column': ['{short_description}', 'key'],
    # 'precision': 2,
    'width': 16
}

# SNMP OID
# Total Swap Size: .1.3.6.1.4.1.2021.4.3.0
# Available Swap Space: .1.3.6.1.4.1.2021.4.4.0
snmp_oid = {
    'default': {'total': '1.3.6.1.4.1.2021.4.3.0', 'free': '1.3.6.1.4.1.2021.4.4.0'},
    'windows': {
        'mnt_point': '1.3.6.1.2.1.25.2.3.1.3',
        'alloc_unit': '1.3.6.1.2.1.25.2.3.1.4',
        'size': '1.3.6.1.2.1.25.2.3.1.5',
        'used': '1.3.6.1.2.1.25.2.3.1.6',
    },
}

# Define the history items list
# All items in this list will be historised if the --enable-history tag is set
items_history_list = [
    {'name': 'percent', 'description': 'Swap memory usage', 'y_unit': '%'}
]


class PluginModel(GlancesPluginModel):
    """Glances swap memory plugin.

    stats is a dict
    """

    def __init__(self, args=None, config=None):
        """Init the plugin."""
        super(PluginModel, self).__init__(
            args=args, config=config,
            items_history_list=items_history_list,
            fields_description=fields_description,
            template=template
        )

        # We want to display the stat in the curse interface
        self.display_curse = True

    @GlancesPluginModel._check_decorator
    @GlancesPluginModel._log_result_decorator
    def update(self):
        """Update swap memory stats using the input method."""
        # Init new stats
        stats = self.get_init_value()

        if self.input_method == 'local':
            # Update stats using the standard system lib
            # Grab SWAP using the psutil swap_memory method
            try:
                sm_stats = psutil.swap_memory()
            except RuntimeError:
                # Crash on startup on Illumos when no swap is configured #1767
                pass
            else:
                # Get all the swap stats (copy/paste of the psutil documentation)
                # total: total swap memory in bytes
                # used: used swap memory in bytes
                # free: free swap memory in bytes
                # percent: the percentage usage
                # sin: the number of bytes the system has swapped in from disk (cumulative)
                # sout: the number of bytes the system has swapped out from disk (cumulative)
                for swap in ['total', 'used', 'free', 'percent', 'sin', 'sout']:
                    if hasattr(sm_stats, swap):
                        stats[swap] = getattr(sm_stats, swap)

                # By storing time data we enable sin/s and sout/s calculations in the
                # XML/RPC API, which would otherwise be overly difficult work
                # for users of the API
                stats['time_since_update'] = getTimeSinceLastUpdate('memswap')
        elif self.input_method == 'snmp':
            # Update stats using SNMP
            if self.short_system_name == 'windows':
                # Mem stats for Windows OS are stored in the FS table
                try:
                    fs_stat = self.get_stats_snmp(snmp_oid=snmp_oid[self.short_system_name], bulk=True)
                except KeyError:
                    self.reset()
                else:
                    for fs in fs_stat:
                        # The virtual memory concept is used by the operating
                        # system to extend (virtually) the physical memory and
                        # thus to run more programs by swapping unused memory
                        # zone (page) to a disk file.
                        if fs == 'Virtual Memory':
                            stats['total'] = int(fs_stat[fs]['size']) * int(fs_stat[fs]['alloc_unit'])
                            stats['used'] = int(fs_stat[fs]['used']) * int(fs_stat[fs]['alloc_unit'])
                            stats['percent'] = float(stats['used'] * 100 / stats['total'])
                            stats['free'] = stats['total'] - stats['used']
                            break
            else:
                stats = self.get_stats_snmp(snmp_oid=snmp_oid['default'])

                if stats['total'] == '':
                    self.reset()
                    return stats

                for key in iterkeys(stats):
                    if stats[key] != '':
                        stats[key] = float(stats[key]) * 1024

                # used=total-free
                stats['used'] = stats['total'] - stats['free']

                # percent: the percentage usage calculated as (total -
                # available) / total * 100.
                stats['percent'] = float((stats['total'] - stats['free']) / stats['total'] * 100)

        # Update the stats
        self.stats = stats

        return self.stats

    def update_views(self):
        """Update stats views."""
        # Call the father's method
        super(PluginModel, self).update_views()

        # Add specifics information
        # Alert and log
        if 'used' in self.stats and 'total' in self.stats and 'percent' in self.stats:
            self.views['percent']['decoration'] = self.get_alert_log(self.stats['used'], maximum=self.stats['total'])

        # if 'trend' in self.fields_description:
        #     self.views[self.fields_description['trend']]['trend'] = self.trend_msg(self.get_trend(self.fields_description['trend']))

    def msg_curse(self, args=None, max_width=None):
        """Return the dict to display in the curse interface."""
        # Init the return message
        ret = []

        # Only process if stats exist and plugin not disabled
        if not self.stats or self.is_disabled():
            return ret

        # First line
        # total%
        msg = '{}'.format('SWAP')
        ret.append(self.curse_add_line(msg, "TITLE"))
        msg = ' {:3}'.format(self.trend_msg(self.get_trend('percent')))
        ret.append(self.curse_add_line(msg))
        # Percent memory usage
        msg = '{:>6.1%}'.format(self.stats['percent'] / 100)
        ret.append(self.curse_add_line(msg, self.get_views(key='percent', option='decoration')))

        # Second line
        # total
        ret.append(self.curse_new_line())
        # Total memory usage
        ret.extend(self.curse_add_stat('total', width=16))

        # Third line
        # used
        ret.append(self.curse_new_line())
        # Used memory usage
        ret.extend(self.curse_add_stat('used', width=16))

        # Fourth line
        # free
        ret.append(self.curse_new_line())
        # Free memory usage
        ret.extend(self.curse_add_stat('free', width=16))

        return ret
