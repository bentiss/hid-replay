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
	usage_page = usage >> 16
	if hid.inv_usage_pages.has_key(usage_page) and \
			hid.inv_usage_pages[usage_page] == "Button":
		usage = "B" + str(usage & 0xFF)
	elif hid.inv_usages.has_key(usage):
		usage = hid.inv_usages[usage]
	else:
		usage = "0x{:04x}".format(usage)
	return usage

def get_value(report, start, size, twos_comp):
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
	if twos_comp and size > 1:
		value = parse_rdesc.twos_comp(value, size)
	return value, end_bit

def dump_report(time, report, rdesc, mt, f_out):
	"""
	Translate the given report to a human readable format.
	Currently only multitouch reports are processed.
	"""
	data = []
	total_bit_offset = 0

	f_out.write("{:>10s} ".format(time))
	sep = ''
	report_descriptor = None
	if len(rdesc.keys()) == 1:
		report_descriptor = rdesc[-1]
	else:
		f_out.write("ReportID: %d " % report[0])
		sep = '/'
		report_descriptor = rdesc[report[0]]
		total_bit_offset = 8 # first byte is report ID, actual data starts at 8
	prev = None
	for report_item in report_descriptor:
		size = report_item["size"]
		array = not (report_item["type"] & (0x1 << 1)) # Variable
		const = report_item["type"] & (0x1 << 0)
		values = []
		usage_page_name = ''
		usage_page = report_item["usage page"] >> 16
		if hid.inv_usage_pages.has_key(usage_page):
			usage_page_name = hid.inv_usage_pages[usage_page]

		# get the value and consumes bits
		for i in xrange(report_item["count"]):
			value, total_bit_offset = get_value(report, total_bit_offset, size, report_item["logical min"] < 0)
			values.append(value)

		if const:
			f_out.write("%s # " % sep)
		elif not array:
			value_format = "{:d}"
			if size > 1:
				value_format = "{:" + str(len(str(1<<size)) + 1) + "d}"
			usage = " " + get_usage(report_item["usage"]) + ':'
			if prev and prev["type"] == report_item["type"] and prev["usage"] == report_item["usage"]:
				sep = ","
				usage = ""
			f_out.write(sep + usage + " " + value_format.format(values[0]) + " ")
		else:
			if not usage_page_name:
				usage_page_name = "Array"
			usages = []
			for v in values:
				if v < report_item["logical min"] or v > report_item["logical max"]:
					usages.append('')
				else:
					usage = "{:02x}".format(v)
					if 'vendor' not in usage_page_name.lower() and v > 0 and v < len(report_item["usages"]):
						usage = get_usage(report_item["usages"][v])
						if "no event indicated" in usage.lower():
							usage = ''
					usages.append(usage)
			f_out.write(sep + usage_page_name + " [" + ", ".join(usages) + "] ")
		sep = '|'
		prev = report_item
	f_out.write("\n")

def parse_hid(f_in, f_out):
	r = None
	while True:
		try:
			line = f_in.readline()
		except KeyboardInterrupt:
			break
		if line.startswith("R:"):
			rdesc, mt, win8 = parse_rdesc.parse_rdesc(line.lstrip("R: "), f_out)
			if win8:
				f_out.write("**** win 8 certified ****\n")
		elif line.startswith("E:"):
			e, time, size, report = line.split(' ', 3)
			report = [ int(item, 16) for item in report.split(' ')]
			dump_report(time, report, rdesc, mt, f_out)
		elif line == '':
			# End of file
			break

def main():
	f = sys.stdin
	if len(sys.argv) > 1:
		f = open(sys.argv[1])
	parse_hid(f, sys.stdout)
	f.close()

if __name__ == "__main__":
	main()
