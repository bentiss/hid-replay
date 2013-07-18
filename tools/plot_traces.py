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
import plot_hid

def main():
	plots = []
	files = []
	if len(sys.argv) > 1:
		files = [open(f) for f in sys.argv]

	for i in xrange(len(files)):
		f = files[i]
		times, xs, ys = [], [], []
		try:
			times, xs, ys = plot_hid.retrieve_t_x_y_from_hid(f)
		except:
			pass
		if len(times) > 0:
			pyplot.plot(times, xs, label="X_hid" + str(i))
			pyplot.hold(True)
			pyplot.plot(times, ys, label="Y_hid" + str(i))
			continue

		f.seek(0)
		try:
			times, xs, ys = plot_evtest.retrieve_t_x_y_from_evtest(f)
		except:
			pass
		if len(times) > 0:
			pyplot.plot(times, xs, label="X_evtest" + str(i))
			pyplot.hold(True)
			pyplot.plot(times, ys, label="Y_evtest" + str(i))
			continue

	pyplot.hold(False)
	pyplot.legend(loc='lower left')

	# Draw the plot to the screen
	pyplot.show()

if __name__ == "__main__":
	main()
