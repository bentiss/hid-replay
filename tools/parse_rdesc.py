#!/bin/env python
# -*- coding: utf-8 -*-
#
# Hid replay / parse_rdesc.py
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
from hid import *

def twos_comp(val, bits):
	"""compute the 2's compliment of int value val"""
	if (val & (1 << (bits - 1))) != 0:
		val = val - (1 << bits)
	return val

def dump_rdesc(r, hid, item, raw_value, value, up, offset, indent):
	"""
	Format the hid item in a lsusb -v format.
	"""
	data = "none"
	rvalues = [ v for v in raw_value ]
	rvalues.reverse()
	if item != "End Collection":
		data = " ["
		for v in rvalues:
			data += " 0x{:02x}".format(v & 0xff)
		data += " ] {}".format(value)
	print "            Item({0:6s}): {1}, data={2}".format(hid_type[item], item, data)
	if item == "Usage":
		usage = up | value
		if usage in inv_usages.keys():
			print "                ", inv_usages[usage]

def dump_rdesc_array(r, hid, item, raw_value, value, up, offset, indent):
	"""
	Format the hid item in a C-style format.
	"""
	line = "0x{:02x}, ".format(r & 0xff)
	rvalues = [ v for v in raw_value ]
	rvalues.reverse()
	for v in rvalues:
		line += "0x{:02x}, ".format(v & 0xff)
	line += " " * (30 - len(line))

	if item == "End Collection":
		indent -= 1

	descr = '  ' * indent + item
	if item in ("Report ID",
		    "Usage Minimum",
		    "Usage Maximum",
		    "Logical Minimum",
		    "Logical Maximum",
		    "Physical Minimum",
		    "Physical Maximum",
		    "Report Size",
		    "Report Count",
		    "Unit Exponent"):
		descr +=  " (" + str(value) + ')'
	elif item == "Collection":
		descr +=  " (" + inv_collections[value].capitalize() + ')'
		indent += 1
	elif item == "Usage Page":
		if inv_usage_pages.has_key(value):
			descr +=  " (" + inv_usage_pages[value] + ')'
		else:
			descr +=  " (Vendor Usage Page 0x{:02x})".format(value)
	elif item == "Usage":
		usage = value | up
		if inv_usages.has_key(usage):
			descr +=  " (" + inv_usages[usage] + ')'
		else:
			descr +=  " (Vendor Usage 0x{:02x})".format(value)
	elif item == "Input" \
	  or item == "Output" \
	  or item == "Feature":
		descr +=  " ("
		if value & (0x1 << 0):
			descr += "Cnst,"
		else:
			descr += "Data,"
		if value & (0x1 << 1):
			descr += "Var,"
		else:
			descr += "Arr,"
		if value & (0x1 << 2):
			descr += "Rel"
		else:
			descr += "Abs"
		if value & (0x1 << 3):
			descr += ",Wrap"
		if value & (0x1 << 4):
			descr += ",NonLin"
		if value & (0x1 << 5):
			descr += ",NoPref"
		if value & (0x1 << 6):
			descr += ",Null"
		if value & (0x1 << 7):
			descr += ",Vol"
		if value & (0x1 << 8):
			descr += ",Buff"
		descr +=  ")"
	elif item == "Unit":
		systems = ("None", "SILinear", "SIRotation", "EngLinear", "EngRotation")
		lengths = ("None", "Centimeter", "Radians", "Inch", "Degrees")
		masses = ("None", "Gram", "Gram", "Slug", "Slug")
		times = ("Seconds","Seconds","Seconds","Seconds")
		temperatures = ("None", "Kelvin", "Kelvin", "Fahrenheit", "Fahrenheit")
		currents = ("Ampere","Ampere","Ampere","Ampere")
		luminous_intensisties = ("Candela","Candela","Candela","Candela")
		units = (lengths, masses, times, temperatures, currents, luminous_intensisties)

		system = value & 0xf

		descr +=  " ("
		for i in xrange(len(units), 0, -1):
			v = (value >> i*4) & 0xf
			v = twos_comp(v, 4)
			if v:
				descr += units[i - 1][system]
				if v != 1:
					descr += '^' + str(v)
				descr += ","
		descr += systems[system] + ')'
	elif item == "Push":
		pass
	elif item == "Pop":
		pass
	descr += " " * (35 - len(descr))
	print line, "//", descr, offset
	return indent

def parse_rdesc(rdesc_str, show = False):
	"""
	Parse the given report descriptor and outputs it to stdout if show is True.
	Returns:
	 - a parsed dict of each report indexed by their report ID
	 - the id of the multitouch collection, or -1
	 - if the multitouch device has been Win 8 certified
	"""
	mt_report_id = -1
	reports = {}

	rdesc = [int(r, 16) for r in rdesc_str.split(' ')]
	index = 1 # 0 is the size
	usage_page = 0
	usage_page_list = []
	usage = []
	count = 0
	size = 0
	report = []
	report_ID = -1
	win8 = False
	indent = 0

	while index < len(rdesc):
		r = rdesc[index]
		raw_value = []
		hid = r & 0xfc
		try:
			item = inv_hid[hid]
		except:
			error = "error while parsing " + str(index) + " at " + str(rdesc_str.split(" ")[max(0, index - 5):index + 6])
			raise KeyError, error
		rsize = r & 0x3
		if rsize == 3:
			rsize = 4
		value = 0
		for i in xrange(rsize, 0, -1):
			raw_value.append(rdesc[index + i])
			value |= rdesc[index + i] << (i-1)*8;

		if rsize > 0 and item in ("Logical Minimum",
					  "Logical Maximum",
					  "Physical Minimum",
					  "Physical Maximum"):
			value = twos_comp(value, rsize * 8)

		if item == "Unit Exponent":
			if value > 7:
				value -= 16

		if show:
			indent = dump_rdesc_array(r, hid, item, raw_value, value, usage_page, index - 1, indent)

		index += 1 + rsize

		if item == "Report ID":
			if report_ID:
				reports[report_ID] = report
				report = []
			report_ID = value
		elif item == "Push":
			usage_page_list.append(usage_page)
		elif item == "Pop":
			usage_page = usage_page_list.pop()
		elif item == "Usage Page":
			usage_page = value << 16
		elif item == "Usage":
			usage.append(value | usage_page)
			if value | usage_page == 0xd0051:
				mt_report_id = report_ID
		elif item == "Report Count":
			count = value
		elif item == "Report Size":
			size = value
		elif item == "Input":
			if len(usage) == 0:
				usage = 0
			elif len(usage) == count:
				for i in xrange(count):
					report.append((usage[i], size))
				usage = []
				continue
			else:
				usage = usage[-1]
			report.append((usage, count * size))
			usage = []
		elif item == "Feature":
			if usage[-1] == 0xff0000c5:
				win8 = True
	if report_ID:
		reports[report_ID] = report
		report = []

	return reports, mt_report_id, win8

def main():
	f = open(sys.argv[1])
	for line in f.readlines():
		if line.startswith("R:"):
			parse_rdesc(line.lstrip("R: "), True)
			break
	f.close()

if __name__ == "__main__":
    main()
