#!/bin/env python
# -*- coding: utf-8 -*-
#
# Hid replay / plot_hid.py
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
import os
import parse_hid
import matplotlib.pyplot as pyplot
import plot_evtest

def retrieve_t_x_y_from_hid(f):
	times = []
	xs = []
	ys = []
	start_time = -1
	tmp_out = os.tmpfile()
	parse_hid.parse_hid(f, tmp_out)
	tmp_out.seek(0)
	while True:
		try:
			line = tmp_out.readline()
		except KeyboardInterrupt:
			break
		if "X:" in line:
			line = line.strip()
			data = line.split()
			time = float(data[0])
			if start_time < 0:
				start_time = time
			time -= start_time
			x = int(data[data.index("X:") + 1])
			y = int(data[data.index("Y:") + 1])
			times.append(time)
			xs.append(x)
			ys.append(y)
		elif line == '':
			# End of file
			break
	tmp_out.close()
	return times, xs, ys


def main():
	f = sys.stdin
	if len(sys.argv) > 1:
		f = open(sys.argv[1])
	times, xs, ys = retrieve_t_x_y_from_hid(f)
	f.close()

	pyplot.plot(times, xs, label="X")
	pyplot.hold(True)
	pyplot.plot(times, ys, label="Y")
	pyplot.hold(False)
	pyplot.legend(loc='lower left')

	# Draw the plot to the screen
	pyplot.show()

if __name__ == "__main__":
	main()
