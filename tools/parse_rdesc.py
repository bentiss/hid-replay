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

class raw_item(object):
	def __init__(self, report, index):
		self.report = report
		self.index = index
		self.__parse()

	def __parse(self):
		self.r = r = self.report[self.index]
		self.raw_value = raw_value = []
		self.hid = r & 0xfc
		try:
			item = inv_hid[self.hid]
		except:
			error = "error while parsing " + str(self.index) + " at " + str(["%02x"%(i) for i in self.report[max(0, index - 5):index + 6]])
			raise KeyError, error
		self.rsize = r & 0x3
		if self.rsize == 3:
			self.rsize = 4
		self.value = 0
		for i in xrange(self.rsize, 0, -1):
			raw_value.append(self.report[self.index + i])
			self.value |= self.report[self.index + i] << (i-1)*8;

		if item == "Unit Exponent":
			if self.value > 7:
				self.value -= 16

	def next(self):
		return self.index + 1 + self.rsize

	def item(self):
		return inv_hid[self.hid]

	def twos_comp(self):
		if self.rsize:
			self.value = twos_comp(self.value, self.rsize * 8)
		return self.value



def dump_rdesc(rdesc_item, indent):
	"""
	Format the hid item in a lsusb -v format.
	"""
	raw_value = rdesc_item.raw_value
	item = rdesc_item.item()
	up = rdesc_item.usage_page
	value = rdesc_item.value
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

def dump_rdesc_array(rdesc_item, indent):
	"""
	Format the hid item in a C-style format.
	"""
	r = rdesc_item.r
	hid = rdesc_item.hid
	item = rdesc_item.item()
	raw_value = rdesc_item.raw_value
	value = rdesc_item.value
	up = rdesc_item.usage_page
	offset = rdesc_item.index
	rsize = rdesc_item.rsize
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
		    "Physical Minimum",
		    "Logical Maximum",
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
	usage_min = 0
	usage_max = 0
	logical_min = 0
	logical_min_item = None
	logical_max = 0
	logical_max_item = None
	count = 0
	size = 0
	report = []
	report_ID = -1
	win8 = False
	rdesc_items = []

	while index < len(rdesc):
		rdesc_item = raw_item(rdesc, index)
		rdesc_items.append(rdesc_item)

		# store current usage_page in rdesc_item
		rdesc_item.usage_page = usage_page

		index = rdesc_item.next()
		item = rdesc_item.item()
		value = rdesc_item.value

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
			# reset the usage list
			usage = []
			usage_min = 0
			usage_max = 0
		elif item == "Collection":
			# reset the usage list
			usage = []
			usage_min = 0
			usage_max = 0
		elif item == "Usage Minimum":
			usage_min = value | usage_page
		elif item == "Usage Maximum":
			usage_max = value | usage_page
		elif item == "Logical Minimum":
			logical_min = value
			logical_min_item = rdesc_item
		elif item == "Logical Maximum":
			logical_max = value
			logical_max_item = rdesc_item
		elif item == "Usage":
			usage.append(value | usage_page)
			if value | usage_page == 0xd0051:
				mt_report_id = report_ID
		elif item == "Report Count":
			count = value
		elif item == "Report Size":
			size = value
		elif item == "Input": # or item == "Output":
			if logical_min > logical_max:
				logical_min = logical_min_item.twos_comp()
				logical_max = logical_max_item.twos_comp()
			item = {"type": value, "usage page": usage_page, "logical min": logical_min, "logical max": logical_max, "size": size, "count": count}
			if value & (0x1 << 0): # Const item
				item["size"] = size * count
				item["count"] = 1
				report.append(item)
			elif value & (0x1 << 1): # Variable item
				if usage_min and usage_max:
					usage = usage_min
					for i in xrange(count):
						item = item.copy()
						item["count"] = 1
						item["usage"] = usage
						report.append(item)
						if usage < usage_max:
							usage += 1
				else:
					for i in xrange(count):
						usage_ = 0
						if i < len(usage):
							usage_ = usage[i]
						else:
							usage_ = usage[-1]
						item = item.copy()
						item["count"] = 1
						item["usage"] = usage_
						report.append(item)
			else: # Array item
				if usage_min and usage_max:
					usage = range(usage_min, usage_max + 1)
				item["usages"] = usage
				report.append(item)
			usage = []
			usage_min = 0
			usage_max = 0
		elif item == "Feature":
			if usage[-1] == 0xff0000c5:
				win8 = True
	if report_ID:
		reports[report_ID] = report
		report = []

	if show:
		indent = 0
		for rdesc_item in rdesc_items:
			indent = dump_rdesc_array(rdesc_item, indent)

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
