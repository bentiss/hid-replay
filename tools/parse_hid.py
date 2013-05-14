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

def dump_report(time, report, rdesc, mt):
	"""
	Translate the given report to a human readable format.
	Currently only multitouch reports are processed.
	"""
	data = []
	total_bit_offset = 0

	print time,
	sep = ''
	report_descriptor = None
	if len(rdesc.keys()) == 1:
		report_descriptor = rdesc[-1]
	else:
		print "ReportID:", report[0],
		sep = '/'
		report_descriptor = rdesc[report[0]]
		total_bit_offset = 8 # first byte is report ID, actual data starts at 8
	for usage, size in report_descriptor:
		value = 0
		start_bit = total_bit_offset
		end_bit = start_bit + size
		data = report[start_bit / 8 : end_bit / 8 + 1]
		for d in xrange(len(data)):
			value |= data[d] << (8 * d)

		bit_offset = total_bit_offset % 8
		value = value >> bit_offset
		garbage = (value >> size) << size
		value = value - garbage
		value = parse_rdesc.twos_comp(value, size)
		total_bit_offset = end_bit
		if hid.inv_usages.has_key(usage):
			usage = hid.inv_usages[usage]
		else:
			usage = "0x{:04x}".format(usage)
		value_format = "{:" + str(len(str(1<<size)) + 1) + "d}"
		print sep, usage + ':', value_format.format(value),
		sep = '|'
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
