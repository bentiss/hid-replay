#!/bin/env python
# -*- coding: utf-8 -*-
#
# Hid replay / hid.py: table of hid usages and definitions
#
# Copyright (c) 2012-2013 Benjamin Tissoires <benjamin.tissoires@gmail.com>
# Copyright (c) 2012-2013 Red Hat, Inc.
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

import sys
import re
import parse_hut

hid_items = {
	"Main": {
		"Input"			:0b10000000,
		"Output"		:0b10010000,
		"Feature"		:0b10110000,
		"Collection"		:0b10100000,
		"End Collection"	:0b11000000,
	},

	"Global": {
		"Usage Page"		:0b00000100,
		"Logical Minimum"	:0b00010100,
		"Logical Maximum"	:0b00100100,
		"Physical Minimum"	:0b00110100,
		"Physical Maximum"	:0b01000100,
		"Unit Exponent"		:0b01010100,
		"Unit"			:0b01100100,
		"Report Size"		:0b01110100,
		"Report ID"		:0b10000100,
		"Report Count"		:0b10010100,
		"Push"			:0b10100100,
		"Pop"			:0b10110100,
	},

	"Local": {
		"Usage"			:0b00001000,
		"Usage Minimum"		:0b00011000,
		"Usage Maximum"		:0b00101000,
		"Designator Index"	:0b00111000,
		"Designator"		:0b01001000,
		"Designator"		:0b01011000,
		"String Index"		:0b01111000,
		"String Minimum"	:0b10001000,
		"String Maximum"	:0b10011000,
		"Delimiter"		:0b10101000,
	},
}

collections = {
	'PHYSICAL'		:0,
	'APPLICATION'		:1,
	'LOGICAL'		:2,
}

inv_hid = {}
hid_type = {}
for type, items in hid_items.iteritems():
	for k, v in items.iteritems():
		inv_hid[v] = k
		hid_type[k] = type

usages = parse_hut.parse()

inv_usage_pages = {}
inv_usages = {}
for usage, (name, filename, usage_list) in usages.iteritems():
	inv_usage_pages[usage] = name
	for k, v in usage_list.iteritems():
		inv_usages[(usage << 16) | k] = v

inv_collections = dict([(v, k) for k, v in collections.iteritems()])
