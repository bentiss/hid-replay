#!/bin/env python3
# -*- coding: utf-8 -*-
#
# Hid replay / parse_hid.py: generate a table of hid usages and definitions
#
# Copyright (c) 2012-2017 Benjamin Tissoires <benjamin.tissoires@gmail.com>
# Copyright (c) 2012-2017 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import os

DATA_DIRNAME = "data"
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, DATA_DIRNAME)


def parse_usages(usage_list):
    usages = {}
    idx, page_name = None, None
    for line in usage_list:
        line = line.strip()
        if not line:
            continue
        if line.startswith('('):
            idx, page_name = line.split('\t')
            idx = int(idx.lstrip('(').rstrip(')'))
            continue
        usage, name = line.split('\t')
        if 'reserved' in name.lower():
            continue
        if '-' in usage:
            print(line)
            continue
        usages[int(usage, 16)] = name
    return idx, page_name, usages


def parse():
    usages = {}
    for filename in os.listdir(DATA_DIR):
        if filename.endswith('.hut'):
            with open(os.path.join(DATA_DIR, filename), 'r') as f:
                try:
                    idx, name, usages_list = parse_usages(f.readlines())
                    usages[idx] = (name, filename, usages_list)
                except UnicodeDecodeError:
                    print(filename)
                    raise
    return usages
