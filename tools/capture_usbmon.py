#!/bin/env python
# -*- coding: utf-8 -*-
#
# Hid replay / capture_usbmon.py
#
# must be run as root.
#
# This program is useful to capture both the raw usb events from an input
# device and its kernel generated events.
#
# Requires several tools to be installed: usbmon, evemu and pyudev
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

import os
import sys
import threading
import subprocess
import shlex
import time
from optparse import OptionParser
import pyudev
import inspect


module_path = os.path.abspath(inspect.getsourcefile(lambda _: None))
module_dirname = os.path.dirname(module_path)
usbmon2hid_replay = module_dirname + "/usbmon2hid-replay.py"

class UDevObject(object):
	""" Abstract class for an udev tree element"""
	def __init__(self, device, parent, children_class):
		"device being an udev device"
		self.device = device
		self.parent = parent
		self.children_class = children_class
		self.childrens = {}
		self.bind_file = None

	def is_child_type(self, other):
		"is the other UDevObject from the correct child type"
		# abstract method, has to be overwritten in the subclasses
		return False

	def is_parent(self, other):
		"true if the current UDevObject is a parent of the given UDevObject"
		return self.device.sys_path in other.sys_path

	def add_child(self, device):
		"""add a child to the hierarchy: instanciate a new subclass of UDevObject
		stored in self.children_class.
		"""
		if not self.children_class:
			return
		child = self.children_class(device, self)
		self.childrens[device.sys_path] = child

	def removed(self):
		"called when the item is removed from the parent"
		# abstract method, has to be overwritten in the subclasses
		pass

	def clean(self):
		"remove all of the children of the UDevObject"
		for child in self.childrens.values():
			child.removed()
			child.clean()
		self.childrens = {}

	def udev_event(self, action, device):
		"called when a udev event is processed"
		if self.is_child_type(device):
			# the device is our direct child, add/remove it to the hierarchy
			if action == "add":
				self.add_child(device)
			else:
				if device.sys_path in self.childrens.keys():
					# be sure to notify the "removed" call before deleting it
					self.childrens[device.sys_path].removed()
					del(self.childrens[device.sys_path])
		else:
			# maybe our children know how to handle it
			for child in self.childrens.values():
				if child.is_parent(device):
					child.udev_event(action, device)

	def get_name(self):
		"return a more convenient name for the current object"
		return self.device.sys_path

	def print_tree(self, level = 0):
		"convenient function to print a tree of the current known devices"
		print self.get_name()
		for child in self.childrens.values():
			print ("  " * level) + u'  └',
			child.print_tree(level + 1)

	def unbind(self):
		"unbind the device from its current driver"
		path = self.device.sys_path
		unbind_path = "{0}/driver/unbind".format(path)
		bind_path = "{0}/driver/bind".format(path)
		if not os.path.exists(unbind_path):
			return False
		self.unbind_file = open(unbind_path, "w")
		self.bind_file = open(bind_path, "w")

		self.unbind_file.write(self.device.sys_name)
		self.unbind_file.close()
		return True

	def rebind(self):
		"rebind the device to its driver (unbind has to be called first)"
		if not self.bind_file:
			raise Exception, "trying to rebind an unbind device"

		self.bind_file.write(self.device.sys_name)
		self.bind_file.close()
		self.bind_file = None

class EventNode(UDevObject):
	def __init__(self, device, parent):
		# no children devices for this one
		UDevObject.__init__(self, device, parent, None)
		self.index = int(self.device.sys_name.replace("event", ""))
		self.start_evemu()

	def get_name(self):
		return "{0}_{1}.ev".format(self.parent.get_name(), self.index)

	def removed(self):
		# close the underlying evemu process when the device is removed
		self.p.terminate()
		self.p.wait()
		self.output.close()

	def start_evemu(self):
		# start an evemu-record of the event node
		print "dumping evdev events in", self.get_name()
		self.output = open(self.get_name(), 'w')
		evemu_command = "evemu-record /dev/input/{0}".format(self.device.sys_name)
		print evemu_command
		self.p = subprocess.Popen(shlex.split(evemu_command), stdout=self.output)


class USBInterface(UDevObject):
	def __init__(self, device, parent):
		UDevObject.__init__(self, device, parent, EventNode)
		self.intf_number = device.sys_name.split(':')[-1]
		self.lsusb()

	def is_child_type(self, other):
		return other.subsystem == u'input' and u'event' in other.sys_name

	def get_name(self):
		return "{0}_{1}".format(self.parent.get_name(), self.intf_number)

	def write_hid_file(self):
		"convert the usbmon recording into a hid recording"
		intf = self.intf_number.split(".")[-1]
		usbmon = self.parent.get_usbmon_filename()
		usbmon_command = "python {0} {1} --intf {2}".format(usbmon2hid_replay, usbmon, intf)
		f = open(self.get_name() + ".hid", "w")
		p = subprocess.Popen(shlex.split(usbmon_command), stdout=f)
		p.wait()
		print "written", self.get_name() + ".hid"

	def removed(self):
		self.parent.remove_interface(self)

	def lsusb(self):
		"""when the usb driver does not checks for the report descriptors, we have
		to ask them ourself: call `lsusb -v' when the driver is not bound."""
		# unbind the device first
		if not self.unbind():
			return

		# call lsusb -v
		lsusbcall = "lsusb -v -d {0}:{1}".format(self.parent.vid, self.parent.pid)
		subprocess.call(shlex.split(lsusbcall), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

		#rebind the device
		self.rebind()

class USBDev(UDevObject):
	""" A USB device object:
	- will keep the interface hierarchy
	- at unplug, convert the usb recording into the various hid files (one
	  per known interface)
	"""
	def __init__(self, device):
		UDevObject.__init__(self, device, None, USBInterface)
		self.vid = device.get("ID_VENDOR_ID")
		self.pid = device.get("ID_MODEL_ID")
		self.vendor = device.get("ID_VENDOR").replace(".", "")
		self.start_usbmon()
		self.removed_intf = []

	def is_child_type(self, other):
		return other.device_type == u'usb_interface'

	def get_name(self):
		return "{0}_{1}_{2}".format(self.vendor, self.vid, self.pid)

	def get_usbmon_filename(self):
		"return the usbmon file name were the events are recorded"
		return self.get_name() + ".usbmon"

	def start_usbmon(self):
		"start the usbmon subprocess"
		number = self.device.device_node.split('/')[-1]
		bus = int(self.device.device_node.split('/')[-2])

		# start usbmon
		print "dumping usb events in", self.get_usbmon_filename()
		self.usbmon_file = open(self.get_usbmon_filename(), 'w')
		USBMon.add_listener(bus, number, self.usbmon_file)

	def remove_interface(self, intf):
		"when an interface is removed, this method is called"
		self.removed_intf.append(intf)

	def terminate(self):
		"""clean up and terminate the usb device:
		- stop the usbmon capture for this device
		- remove any zombi child
		- ask for each known interface to translate the usbmon capture into a hid one
		"""
		number = self.device.device_node.split('/')[-1]
		bus = int(self.device.device_node.split('/')[-2])
		USBMon.remove_listener(bus, number)
		self.usbmon_file.close()
		self.clean()
		for intf in self.removed_intf:
			intf.write_hid_file()

class USBMon(threading.Thread):
	"""usbmon recorder class:
	- calling a new object USBMon(bus) starts recording usb events on this bus
	- each device gets buffered in its own queue of events
	- when someone add a listener for a specific device, the buffered events are
	  dumped into the given file and each new event is dumped too
	"""
	busses = {}
	def __init__(self, bus):
		threading.Thread.__init__(self)
		self.bus = bus
		USBMon.busses[bus] = self
		self.devices = {}
		self.bufs = {}
		# launch the actual usbmon tool with a buffer big enough to store
		# the various hid report descriptors
		self.p = subprocess.Popen(shlex.split("usbmon -i {0} -fu -s 512".format(bus)), stdout=subprocess.PIPE)
		self.start()

	def pump_events(self, addr):
		"""matches the given device with the current listeners and dumps
		the queue of events into the correct listener"""
		if not addr in self.devices.keys():
			# no listener found, keep the events for later
			return
		while len(self.bufs[addr]) > 0:
			line = self.bufs[addr].pop(0)
			self.devices[addr].write(line)

	def run(self):
		while self.p:
			line = self.p.stdout.readline()
			if not line:
				# end of capture
				break

			# extract the device address
			tag, timestamp, event_type, address, status, usbmon_data = line.rstrip().split(" ", 5)
			URB_type, bus, dev_address, endpoint = address.split(":")
			key_addr = USBMon.create_key(bus, dev_address)

			if not self.bufs.has_key(key_addr):
				# new device, add a new queue to the list
				self.bufs[key_addr] = []

			# add the event to the queue
			self.bufs[key_addr].append(line)

			# try flushing the event into the listeners
			self.pump_events(key_addr)

	def stop(self):
		p = self.p
		if not p:
			return
		self.p = None
		p.terminate()

	@classmethod
	def create_key(cls, bus, number):
		"create a uniq key for a given usb device (bus, number)"
		return "{0}:{1}:".format(bus, number)

	@classmethod
	def add_listener(cls, bus, number, file):
		"append a listener (an opened writable file) for a given usb device"
		if not cls.busses.has_key(bus):
			USBMon(bus)
		usbmon = cls.busses[bus]
		usbmon.devices[cls.create_key(bus, number)] = file

	@classmethod
	def remove_listener(cls, bus, number):
		"remove the listener from the given usb device"
		usbmon = cls.busses[bus]
		del(usbmon.devices[cls.create_key(bus, number)])

	@classmethod
	def terminate_usbmon(cls):
		"terminate all instances of usbmon tools"
		for usbmon in cls.busses.values():
			usbmon.stop()
		cls.busses = {}

class Conductor(object):
	""" In charge of reading udev events and launching the various
	external program."""
	def __init__(self):
		self.context = pyudev.Context()
		# create udev notification system
		self.monitor = pyudev.Monitor.from_netlink(pyudev.Context())
		self.monitor.filter_by('input')
		self.monitor.filter_by('usb')
		self.cv = threading.Condition()
		self.done = False
		self.devices = {}
		self.start_usbmon()
		self.observer = pyudev.MonitorObserver(self.monitor, self.udev_event)

	def start_usbmon(self):
		"look for any root hub and start usbmon on every found one"
		for device in self.context.list_devices(subsystem='usb', DEVTYPE='usb_device'):
			id_model = device.get('ID_MODEL_FROM_DATABASE')
			if id_model and " root hub" in id_model:
				USBMon(int(device.get('BUSNUM')))

	def start(self):
		"start monitoring udev events"
		self.observer.start()

	def stop(self):
		"stop monitoring udev events"
		self.observer.stop()
		self.cv.acquire()
		self.done = True
		self.cv.notify()
		self.cv.release()

	def wait(self):
		"wait for the user to hit ctrl-C to terminate the monitoring/recording"
		self.cv.acquire()
		try:
			while not self.done:
				self.cv.wait(timeout=1.0)
		except (KeyboardInterrupt, SystemExit):
			print ""
			self.stop()
		self.cv.release()

	def print_tree(self):
		"convenient function to print a tree of the current known devices"
		for usb in self.devices.values():
			usb.print_tree()

	def udev_event(self, action, device):
		"called when an udev event is processed"
#		print action, device
		if device.device_type == u'usb_device':
			# the device is a new usb device (hub), add/remove it to
			# the tree
			if action == "add":
				usb = USBDev(device)
				self.devices[device.sys_path] = usb
			else:
				if device.sys_path in self.devices.keys():
					usb = self.devices[device.sys_path]
					del(self.devices[device.sys_path])
					# stopping all captures and flush the various files
					usb.terminate()
		else:
			# this device is unknown at this level, maybe the usb device
			# knows how to handle it
			for usb in self.devices.values():
				if usb.is_parent(device):
					usb.udev_event(action, device)

	def flush(self):
		for usb in self.devices.values():
			usb.terminate()
		USBMon.terminate_usbmon()

def get_options():
	description = \
"""
%prog will capture several traces from the plugged USB devices:
the raw usb events, the evemu events generated by the kernel, and if possible
will convert the usb events into hid events for later replay.
Be careful when recording events (from keyboards for instance), it _can_ (will)
record any password you type, so use it carefully.
"""
	parser = OptionParser(description=description)
#	parser.add_option("", "--intf", dest="intf",
#			help="capture only the given interface number, omit if you don't want to filter")
	return parser.parse_args()

def main():
	(options, args) = get_options()
	conductor = Conductor()
	conductor.start()
	print """
This program will capture the usb raw events, the kernel emitted input events
and also will convert the usb capture into a HID recording.

Please now plug any device you wish to capture, make some events with it, and
unplug it when you have finished. You can plug/unplug several different devices
at the same time, but only the latest recordings from each device will be kept.

Hit Ctrl-C to terminate the program.
"""
	conductor.wait()
	conductor.flush()

if __name__ == "__main__":
	main()
