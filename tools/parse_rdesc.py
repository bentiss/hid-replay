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

type_output = "default"

class ParseError(Exception): pass

class raw_item(object):
	def __init__(self, value, index):
		self.__parse(value)
		self.index_in_report = index
		self.data = None

	def __parse(self, value):
		self.r = r = value
		self.raw_value = []
		self.hid = r & 0xfc
		try:
			self.item = inv_hid[self.hid]
		except:
			error = "error while parsing {0:02x}".format(value)
			if self.hid == 0:
				raise ParseError, error
			else:
				raise KeyError, error
		self.rsize = r & 0x3
		if self.rsize == 3:
			self.rsize = 4
		self.index = self.rsize
		self.value = 0

	def feed(self, value):
		"return True if the value was accepted by the item"
		if self.index <= 0:
			raise ParseError, "this item is already full"
		self.raw_value.append(value)
		self.value |= value << (self.rsize - self.index) * 8;
		self.index -= 1

		if self.index == 0:
			if self.item in ("Logical Minimum",
					 "Physical Minimum",
#					 "Logical Maximum",
#					 "Physical Maximum",
					):
				self.twos_comp()
			if self.item == "Unit Exponent" and self.value > 7:
				self.value -= 16

	def completed(self):
		# if index is null, then we have consumed all the incoming data
		return self.index == 0

	def twos_comp(self):
		if self.rsize:
			self.value = twos_comp(self.value, self.rsize * 8)
		return self.value

	def size(self):
		return 1 + len(self.raw_value)

	def __repr__(self):
		data = ["{0:02x}".format(i) for i in self.raw_value]
		r = "{0:02x}".format(self.r)
		if not len(data):
			return r
		return r + " " + " ".join(data)

class ReportDescriptor(object):
	def __init__(self):
		self.reports = {}
		self.index =  1 # 0 is the size
		self.usage_page = 0
		self.usage_page_list = []
		self.usage = []
		self.usage_min = 0
		self.usage_max = 0
		self.logical_min = 0
		self.logical_min_item = None
		self.logical_max = 0
		self.logical_max_item = None
		self.count = 0
		self.item_size = 0
		self.report = []
		self.report_ID = -1
		self.win8 = False
		self.rdesc_items = []
		self.r_size = 0
		self.current_item = None

	def consume(self, value, index):
		""" item is an int8 """
		if not self.current_item:
			# initial state
			self.current_item = raw_item(value, index)
		else:
			# try to feed the value to the current item
			self.current_item.feed(value)
		if self.current_item.completed():
			rdesc_item = self.current_item
			self.rdesc_items.append(rdesc_item)

			self.parse_item(rdesc_item)
			self.current_item = None

			return rdesc_item
		return None

	def close_rdesc(self):
		if self.report_ID and self.r_size > 8:
			self.reports[self.report_ID] = self.report, (self.r_size >> 3)
			self.report = []
			self.r_size = 0

	def parse_item(self, rdesc_item):
		# store current usage_page in rdesc_item
		rdesc_item.usage_page = self.usage_page
		item = rdesc_item.item
		value = rdesc_item.value

		if item == "Report ID":
			if self.report_ID and self.r_size > 8:
				self.reports[self.report_ID] = self.report, (self.r_size >> 3)
			self.report = []
			self.report_ID = value
			self.r_size = 8
		elif item == "Push":
			self.usage_page_list.append(self.usage_page)
		elif item == "Pop":
			self.usage_page = self.usage_page_list.pop()
		elif item == "Usage Page":
			self.usage_page = value << 16
			# reset the usage list
			self.usage = []
			self.usage_min = 0
			self.usage_max = 0
		elif item == "Collection":
			# reset the usage list
			self.usage = []
			self.usage_min = 0
			self.usage_max = 0
		elif item == "Usage Minimum":
			self.usage_min = value | self.usage_page
		elif item == "Usage Maximum":
			self.usage_max = value | self.usage_page
		elif item == "Logical Minimum":
			self.logical_min = value
			self.logical_min_item = rdesc_item
		elif item == "Logical Maximum":
			self.logical_max = value
			self.logical_max_item = rdesc_item
		elif item == "Usage":
			self.usage.append(value | self.usage_page)
		elif item == "Report Count":
			self.count = value
		elif item == "Report Size":
			self.item_size = value
		elif item == "Input": # or item == "Output":
#			if self.logical_min > self.logical_max:
#				self.logical_min = self.logical_min_item.twos_comp()
#				self.logical_max = self.logical_max_item.twos_comp()
			item = {"type": value,
				"usage page": self.usage_page,
				"logical min": self.logical_min,
				"logical max": self.logical_max,
				"size": self.item_size,
				"count": self.count}
			if value & (0x1 << 0): # Const item
				item["size"] = self.item_size * self.count
				item["count"] = 1
				self.report.append(item)
				self.r_size += self.item_size * self.count
			elif value & (0x1 << 1): # Variable item
				if self.usage_min and self.usage_max:
					usage = self.usage_min
					for i in xrange(self.count):
						item = item.copy()
						item["count"] = 1
						item["usage"] = usage
						self.report.append(item)
						self.r_size += self.item_size
						if usage < self.usage_max:
							usage += 1
				else:
					for i in xrange(self.count):
						usage_ = 0
						if i < len(self.usage):
							usage_ = self.usage[i]
						else:
							usage_ = self.usage[-1]
						item = item.copy()
						item["count"] = 1
						item["usage"] = usage_
						self.report.append(item)
						self.r_size += self.item_size
			else: # Array item
				if self.usage_min and self.usage_max:
					self.usage = range(self.usage_min, self.usage_max + 1)
				item["usages"] = self.usage
				self.report.append(item)
				self.r_size += self.item_size * self.count
			rdesc_item.data = item
			self.usage = []
			self.usage_min = 0
			self.usage_max = 0
		elif item == "Feature":
			if len(self.usage) > 0 and self.usage[-1] == 0xff0000c5:
				self.win8 = True

	def dump(self, dump_file):
		indent = 0
		for rdesc_item in self.rdesc_items:
			if type_output == "default":
				indent = dump_rdesc_array(rdesc_item, indent, dump_file)
			else:
				indent = dump_rdesc_kernel(rdesc_item, indent, dump_file)

	def dump_raw(self, dumpfile):
		dumpfile.write(self.data_txt())

	def size(self):
		size = 0
		for rdesc_item in self.rdesc_items:
			size += rdesc_item.size()
		return size

	def data(self):
		string = self.data_txt()
		data = [int(i, 16) for i in string.split()]
		return data

	def data_txt(self):
		return " ".join([str(i) for i in self.rdesc_items])

def dump_rdesc(rdesc_item, indent, dump_file):
	"""
	Format the hid item in a lsusb -v format.
	"""
	item = rdesc_item.item()
	up = rdesc_item.usage_page
	value = rdesc_item.value
	data = "none"
	if item != "End Collection":
		data = " ["
		for v in rdesc_item.raw_value:
			data += " 0x{:02x}".format(v & 0xff)
		data += " ] {}".format(value)
	dump_file.write("            Item({0:6s}): {1}, data={2}\n".format(hid_type[item], item, data))
	if item == "Usage":
		usage = up | value
		if usage in inv_usages.keys():
			dump_file.write("                 " + inv_usages[usage] + "\n")

def get_raw_values(rdesc_item):
	data = str(rdesc_item)
	# prefix each individual value by "0x" and insert "," in between
	data = "0x" + data.replace(" ", ", 0x") + ","
	return data

def get_human_descr(rdesc_item, indent):
	item = rdesc_item.item
	value = rdesc_item.value
	up = rdesc_item.usage_page
	rsize = rdesc_item.rsize
	descr = item
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
	elif item == "End Collection":
		indent -= 1
	elif item == "Usage Page":
		if inv_usage_pages.has_key(value):
			descr +=  " (" + inv_usage_pages[value] + ')'
		else:
			descr +=  " (Vendor Usage Page 0x{:02x})".format(value)
	elif item == "Usage":
		usage = value | up
		if inv_usages.has_key(usage):
			descr +=  " (" + inv_usages[usage] + ')'
		elif up == usage_pages['Sensor'] << 16:
			mod = (usage & 0xF000) >> 8
			usage &= ~0xF000
			mod_descr = sensor_mods[mod]
			descr +=  " (" + inv_usages[usage] + ' | ' + mod_descr + ')'
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
	eff_indent = indent
	if item == "Collection":
		eff_indent -= 1
	return ' ' * eff_indent + descr, indent

def dump_rdesc_kernel(rdesc_item, indent, dump_file):
	"""
	Format the hid item in a C-style format.
	"""
	offset = rdesc_item.index_in_report - 1
	item = rdesc_item.item
	line = get_raw_values(rdesc_item)
	line += "\t" * ((40 - len(line)) / 8)

	descr, indent = get_human_descr(rdesc_item, indent)
	eff_indent = indent

	descr += "\t" * ((52 - len(descr)) / 8)
	#dump_file.write(line + "/* " + descr + " " + str(offset) + " */\n")
	dump_file.write("\t%s/* %s*/\n"%(line, descr))
	return indent

def dump_rdesc_array(rdesc_item, indent, dump_file):
	"""
	Format the hid item in a C-style format.
	"""
	offset = rdesc_item.index_in_report - 1
	item = rdesc_item.item
	line = get_raw_values(rdesc_item)
	line += " " * (30 - len(line))

	descr, indent = get_human_descr(rdesc_item, indent)
	eff_indent = indent

	descr += " " * (35 - len(descr))
	dump_file.write(line + " // " + descr + " " + str(offset) + "\n")
	return indent

def parse_rdesc(rdesc_str, dump_file = None):
	"""
	Parse the given report descriptor and outputs it to stdout if show is True.
	Returns:
	 - a parsed dict of each report indexed by their report ID
	 - the id of the multitouch collection, or -1
	 - if the multitouch device has been Win 8 certified
	"""

	rdesc = [int(r, 16) for r in rdesc_str.split()]
	indent = 0

	rdesc_object = ReportDescriptor()
	for i in xrange(1,len(rdesc)):
		v = rdesc[i]
		if i == len(rdesc) - 1 and v == 0:
			# some device present a trailing 0, skipping it
			break
		rdesc_item = rdesc_object.consume(v, i)

	rdesc_object.close_rdesc()

	if dump_file:
		rdesc_object.dump(dump_file)

	return rdesc_object

def main():
	f = open(sys.argv[1])
	if len(sys.argv) > 2:
		global type_output
		type_output = sys.argv[2]
	for line in f.readlines():
		if line.startswith("R:"):
			parse_rdesc(line.lstrip("R: "), sys.stdout)
			break
	f.close()

if __name__ == "__main__":
    main()
