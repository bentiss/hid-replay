#!/bin/env python
# -*- coding: utf-8 -*-
#
# Hid replay / parse_hid.py
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
import parse_rdesc
import hid

def get_usage(usage):
	if usage == 0x70000:
		return ""
	usage_page = usage >> 16
	if hid.inv_usage_pages.has_key(usage_page) and \
			hid.inv_usage_pages[usage_page] == "Button":
		usage = "B" + str(usage & 0xFF)
	elif hid.inv_usages.has_key(usage):
		usage = hid.inv_usages[usage]
	else:
		usage = "0x{:04x}".format(usage)
	return usage

def get_value(report, start, size):
	value = 0
	start_bit = start
	end_bit = start_bit + size
	data = report[start_bit / 8 : end_bit / 8 + 1]
	for d in xrange(len(data)):
		value |= data[d] << (8 * d)

	bit_offset = start % 8
	value = value >> bit_offset
	garbage = (value >> size) << size
	value = value - garbage
	if size > 1:
		value = parse_rdesc.twos_comp(value, size)
	return value, end_bit

def dump_report(time, report, rdesc, mt):
	"""
	Translate the given report to a human readable format.
	Currently only multitouch reports are processed.
	"""
	data = []
	total_bit_offset = 0

	print "{:>10s}".format(time),
	sep = ''
	report_descriptor = None
	if len(rdesc.keys()) == 1:
		report_descriptor = rdesc[-1]
	else:
		print "ReportID:", report[0],
		sep = '/'
		report_descriptor = rdesc[report[0]]
		total_bit_offset = 8 # first byte is report ID, actual data starts at 8
	prev = None
	for report_item in report_descriptor:
		size = report_item["size"]
		array = not (report_item["type"] & (0x1 << 1)) # Variable
		const = report_item["type"] & (0x1 << 0)
		values = []

		# get the value and consumes bits
		for i in xrange(report_item["count"]):
			value, total_bit_offset = get_value(report, total_bit_offset, size)
			values.append(value)

		if const:
			print sep, '#',
		elif not array:
			value_format = "{:d}"
			if size > 1:
				value_format = "{:" + str(len(str(1<<size)) + 1) + "d}"
			usage = " " + get_usage(report_item["usage"]) + ':'
			if prev and prev["type"] == report_item["type"] and prev["usage"] == report_item["usage"]:
				sep = ","
				usage = ""
			print sep + usage, value_format.format(values[0]),
		else:
			name = "Array"
			usage_page = report_item["usage page"] >> 16
			if hid.inv_usage_pages.has_key(usage_page):
				name = hid.inv_usage_pages[usage_page]
			print sep, name, [get_usage(v | usage_page << 16) for v in values],
		sep = '|'
		prev = report_item
	print ""

def main():
	f = open(sys.argv[1])
	r = None
	for line in f.readlines():
		if line.startswith("R:"):
			rdesc, mt, win8 = parse_rdesc.parse_rdesc(line.lstrip("R: "), True)
			if win8:
				print "**** win 8 certified ****"
		elif line.startswith("E:"):
			e, time, size, report = line.split(' ', 3)
			report = [ int(item, 16) for item in report.split(' ')]
			dump_report(time, report, rdesc, mt)
	f.close()

if __name__ == "__main__":
	main()
