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
import matplotlib.pyplot as pyplot

def retrieve_t_x_y_from_evtest(f):
	times = []
	xs = []
	ys = []
	start_time = -1
	x = 0
	y = 0
	while True:
		try:
			line = f.readline()
		except KeyboardInterrupt:
			break
		if "Event:" in line:
			if "SYN_REPORT" in line:
				data = line.replace(",", "").split()
				time = float(data[2])
				if start_time < 0:
					start_time = time
				time -= start_time
				times.append(time)
				xs.append(x)
				ys.append(y)
			elif "ABS_X" in line:
				data = line.split()
				x = int(data[-1])
			elif "ABS_Y" in line:
				data = line.split()
				y = int(data[-1])
		elif line == '':
			# End of file
			break
	return times, xs, ys

def main():
	f = sys.stdin
	if len(sys.argv) > 1:
		f = open(sys.argv[1])
	times, xs, ys = retrieve_t_x_y_from_evtest(f)
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
