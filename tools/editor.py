#!/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 Benjamin Tissoires <benjamin.tissoires@gmail.com>
# Copyright (c) 2014 Red Hat, Inc.
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

import os,sys
from PyQt4 import QtCore, QtGui, uic

try:
	_fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
	def _fromUtf8(s):
		return s

import parse_rdesc
import parse_hid


class Main(QtGui.QMainWindow):
	def __init__(self, filename):
		QtGui.QMainWindow.__init__(self)
		self.ui = uic.loadUi('HID_editor.ui', self)
		self.prevPosition = 0
		self.auto_changes = False
		self.ui.humanTextEdit.verticalScrollBar().valueChanged.connect(self.ui.rawTextEdit.verticalScrollBar().setValue)
		self.ui.rawTextEdit.verticalScrollBar().valueChanged.connect(self.ui.humanTextEdit.verticalScrollBar().setValue)

#		self.block_events_propagation()
		if filename:
			self.openFile(filename)
#		self.release_events_propagation()

	def block_events_propagation(self):
		if self.auto_changes:
			return
		self.ui.humanTextEdit.verticalScrollBar().valueChanged.disconnect(self.ui.rawTextEdit.verticalScrollBar().setValue)
		self.auto_changes = True

	def release_events_propagation(self):
		if not self.auto_changes:
			return
		self.auto_changes = False
		self.ui.humanTextEdit.verticalScrollBar().valueChanged.connect(self.ui.rawTextEdit.verticalScrollBar().setValue)

	def events_blocked(self):
		return self.auto_changes

	def parseRawRdesc(self):
		human = ""
		input_str = str(self.ui.rawTextEdit.toPlainText()).strip()
		lines = input_str.split("\n")

		rdesc_object = parse_rdesc.ReportDescriptor()
		indent = 0

		if lines[-1].endswith("0x00"):
			# some device present a trailing 0, skipping it
			lines[-1] = lines[-1][:-4]

		for line in lines:
			l = line.replace(",", "").replace("0x", "").replace("-", "")

			rdesc = [int(r, 16) for r in l.split()]

			for v in rdesc:
				rdesc_item = rdesc_object.consume(v, 0)
				if rdesc_item:
					descr, indent = parse_rdesc.get_human_descr(rdesc_item, indent)
					human += descr
			human += "\n"
		self.ui.humanTextEdit.setText(human)

		rdesc_object.close_rdesc()

		return rdesc_object


	def updateRDescFromRaw(self):
		self.block_events_propagation()
		rdesc = self.parseRawRdesc()
		self.update_rdesc(rdesc)
		cursor = self.ui.rawTextEdit.textCursor()
		err_format = QtGui.QTextCharFormat()
		err_format.setBackground(QtGui.QBrush(QtGui.QColor("red")))
		self.redraw()
		self.highlight(self.prevPosition)
		self.ui.humanTextEdit.verticalScrollBar().setValue(self.ui.rawTextEdit.verticalScrollBar().value())
		self.release_events_propagation()

	def setCurrentLine(self, cursor, n):
		cursor.movePosition(QtGui.QTextCursor.Start)
		cursor.movePosition(QtGui.QTextCursor.Down, QtGui.QTextCursor.MoveAnchor, n)

	def highlight(self, lineNumber):
		hi_selection = QtGui.QTextEdit.ExtraSelection()
		hi_selection.format.setBackground(self.palette().alternateBase())
		hi_selection.format.setProperty(QtGui.QTextFormat.FullWidthSelection, QtCore.QVariant(True))

		rCursor = self.ui.rawTextEdit.textCursor()
		self.setCurrentLine(rCursor, lineNumber)
		hi_selection.cursor = rCursor
		hi_selection.cursor.clearSelection()
		self.ui.rawTextEdit.setExtraSelections([hi_selection])

		hCursor = self.ui.humanTextEdit.textCursor()
		self.setCurrentLine(hCursor, lineNumber)
		hi_selection.cursor = hCursor
		hi_selection.cursor.clearSelection()
		self.ui.humanTextEdit.setExtraSelections([hi_selection])

		self.prevPosition = lineNumber

	def rCursorMoved(self):
		cursor = self.ui.rawTextEdit.textCursor()
		self.highlight(cursor.blockNumber())

	def hCursorMoved(self):
		cursor = self.ui.humanTextEdit.textCursor()
		self.highlight(cursor.blockNumber())

	def openFileAction(self):
		fname = QtGui.QFileDialog.getOpenFileName(self, 'Open file', '')
		print fname

	def saveFileAction(self):
		print "saveFileAction"

	def saveAsFileAction(self):
		print "saveAsFileAction"

	def openFile(self, filename):
		if not os.path.exists(filename):
			raise IOError, filename
		f = open(filename)
		rdesc = None
		events = []
		for line in f.readlines():
			if line.startswith("R:"):
				rdesc = parse_rdesc.parse_rdesc(line.lstrip("R: "), None)
				if not rdesc:
					raise IOError, filename
				rdesc = self.update_rdesc(rdesc)
			if line.startswith("E:") or line.startswith("#"):
				events.append(line.strip())
		f.close()
		# everything went fine, store the new configuration
		self.filename = filename
		self.events = events
		self.redraw()
		self.redrawRaw()

	def update_rdesc(self, rdesc):
		self.rdesc_dict = {}
		self.maybe_numbered = False
		for k in rdesc.reports.keys():
			if len(rdesc.reports[k][0]):
				if k == -1:
					self.maybe_numbered = True
				key = parse_hid.build_rkey(k, rdesc.reports[k][1])
				self.rdesc_dict[key] = rdesc.reports[k][0]
		self.rdesc = rdesc

	def redrawRaw(self):
		raws = ""
		for item in self.rdesc.rdesc_items:
			if item.item == "Report ID":
				raws += "----------------------\n"
			raws += parse_rdesc.get_raw_values(item) + "\n"
			if item.item == "Input":
				raws += "\n"
		self.ui.rawTextEdit.setText(raws)

	def redraw(self):
		scrollPosition = self.ui.outputTextBrowser.verticalScrollBar().value()
		data = ""
		for e in self.events:
			if e.startswith("E:"):
				event = parse_hid.parse_event(e, self.rdesc, self.rdesc_dict, self.maybe_numbered)
				if event:
					data += event
					data += "\n"
			else:
				data += e
				data += "\n"
		self.ui.outputTextBrowser.setText(data)
		self.ui.outputTextBrowser.verticalScrollBar().setValue(scrollPosition)

def main():
	app = QtGui.QApplication(sys.argv)
	filename = None
	if len(sys.argv) > 1:
		filename = sys.argv[1]
	try:
		window=Main(filename)
	except IOError:
		sys.exit(1)
	window.show()
	sys.exit(app.exec_())

if __name__ == "__main__":
	main()
