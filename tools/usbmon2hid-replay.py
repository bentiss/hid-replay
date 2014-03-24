#!/bin/env python
# -*- coding: utf-8 -*-
#
# Hid replay / usbmon2hid-replay.py
#
# must be run with: sudo usbmon -i 3 -fu -s 256 | python usbmon2hid-replay.py
# or: python usbmon2hid-replay.py file.txt
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

import sys
nomem = True

class HID_Device(object):
	def __init__(self, bus, id):
		self.bus = bus
		self.id = id
		self.bcdUSB = None
		self.bdeviceClass = None
		self.bdeviceSubClass = None
		self.bdeviceProtocol = None
		self.bMaxPacketSize0 = None
		self.idVendor = None
		self.idProduct = None
		self.bcdDevice = None
		self.iManufacturer = None
		self.iProduct = None
		self.iSerialNumber = None
		self.bNumConfiguration = None
		self.wLANGID = None
		self.rdesc = {}
		self.incomming_data = {}
		self.init_timestamps = {}

def extract_bytes(string):
	data = string.replace(" ", "")
	return [ data[i*2]+data[i*2+1] for i in xrange(len(data) / 2)]

def prep_incoming_data(data):
	length, content = data.split(" = ")
	length = int(length)
	content = extract_bytes(content)
	return length, content

def null_request(params, data, device):
	return

def print_request(params, data, device):
	print data

def parse_desc_request(data):
	length, value = data.split(" = ")
	length = int(length)
	length_v = int(value[0:2], 16)
	if length != length_v:
#		print "MALFORMED USB DESC PACKET"
		return 0, None, None
	type = value[2:4]
	content = extract_bytes(value[4:])
	return length_v, type, content

def parse_desc_device_request(params, data, device):
	length, type, content = parse_desc_request(data)
	if not length:
		return

	device.bcdUSB = int(content[1] + content[0], 16)
	device.bdeviceClass = int(content[2], 16)
	device.bdeviceSubClass = int(content[3], 16)
	device.bdeviceProtocol = int(content[4], 16)
	device.bMaxPacketSize0 = int(content[5], 16)
	device.idVendor = (content[7] + content[6]).upper()
	device.idProduct = (content[9] + content[8]).upper()
	device.bcdDevice = int(content[11] + content[10], 16)
	device.iManufacturer = int(content[12], 16)
	device.iProduct = int(content[13], 16)
	device.iSerialNumber = int(content[14], 16)
	device.bNumConfiguration = int(content[15], 16)

	#print device.bcdUSB, device.bdeviceClass, device.bdeviceSubClass, device.bdeviceProtocol, device.bMaxPacketSize0, "0x{0}:0x{1}".format(device.idVendor, device.idProduct), device.bcdDevice, device.iManufacturer, device.iProduct, device.iSerialNumber, device.bNumConfiguration

def utf16s_to_utf8s(length, string):
	# TODO: do something much better
	result = ""
	for i in xrange(len(string) / 2):
		result += chr(int(string[i*2], 16))
	missings = (length / 2) - len(result)
	result += "."*missings
	return result

def read_le8(array):
	return int(array[0], 16)

def read_le16(array):
	return int(array[1], 16) | (int(array[0], 16) << 8)

class Ctrl(object):pass

def parse_ctrl_parts(params):
	ctrl = params[0]
	out = Ctrl()
	out.bmRequestType = read_le8(ctrl[0:])
	out.bRequest = read_le8(ctrl[1:])
	out.wValue = read_le16(ctrl[2:])
	out.wIndex = read_le16(ctrl[4:])
	out.wLength = read_le16(ctrl[6:])
	return out

def parse_desc_string_request(params, data, device):
	length, type, content = parse_desc_request(data)
	if not length:
		return
	ctrl = parse_ctrl_parts(params)

	if ctrl.wIndex == 0:
		device.wLANGID = "".join(content)
		return

	length -= 2 # remove 2 bytes of prefix (length + type)

	if ctrl.wIndex == device.iManufacturer:
		device.iManufacturer = utf16s_to_utf8s(length, content)
	elif ctrl.wIndex == device.iProduct:
		device.iProduct = utf16s_to_utf8s(length, content)
	elif ctrl.wIndex == device.iSerialNumber:
		device.iSerialNumber = utf16s_to_utf8s(length, content)
#	else:
#		print params, length, type, utf16s_to_utf8s(length, content)

def parse_desc_rdesc_request(params, data, device):
	if data == "0":
		return
	length, content = prep_incoming_data(data)
	ctrl = parse_ctrl_parts(params)
	device.rdesc[ctrl.wIndex] = length, content
#	device.incomming_data.append((timestamp, length, " ".join(content)))
	if nomem:
		print get_description(device, ctrl.wIndex)
		print get_rdesc(device, ctrl.wIndex)
		print get_devinfo(device)

def interrupt(timestamp, status, data, device):
	if data == "0":
		return
	length, content = prep_incoming_data(data)
	_, pipe = status.split(":")
	pipe = int(pipe)
	if not device.incomming_data.has_key(pipe):
		device.incomming_data[pipe] = []
	device.incomming_data[pipe].append((timestamp, length, " ".join(content)))
	if nomem:
		print get_description(device, pipe)
		print get_event(device, pipe, -1)

HID_COMMANDS = {
	"80 06 01": {
		"name": "GET DESCRIPTOR Request DEVICE",
		"request_device": parse_desc_device_request,
		"debug": False,
	},
	"80 06 02": {
		"name": "GET DESCRIPTOR Request CONFIGURATION",
		"request_device": null_request,
		"debug": False,
	},
	"80 06 03": {
		"name": "GET DESCRIPTOR Request STRING",
		"request_device": parse_desc_string_request,
		"debug": False,
	},
	"80 06 06": {
		"name": "GET DESCRIPTOR Request DEVICE",
		"request_device": null_request,
		"debug": False,
	},
	"81 06 22": {
		"name": "GET DESCRIPTOR Request Reports Descriptor",
		"request_device": parse_desc_rdesc_request,
		"debug": False,
	},
	"a1 01": {
		"name": "GET REPORT Request",
		"request_device": null_request,
		"debug": False,
	},
	"21 09": {
		"name": "SET REPORT Request",
		"request_device": null_request,
		"debug": True,
	},
}

def usbmon2hid_replay(f_in):
	hid_devices = {}
	current_request = null_request
	current_params = None
	while True:
		try:
			line = f_in.readline()
		except KeyboardInterrupt:
			break
		if line == "":
			break
		tag, timestamp, event_type, address, status, usbmon_data = line.rstrip().split(" ", 5)
		URB_type, bus, dev_address, endpoint = address.split(":")
		if not hid_devices.has_key(dev_address):
			hid_devices[dev_address] = HID_Device(bus, dev_address)

		if URB_type == 'Ci': # synchronous control
			if event_type == 'C': # answer
				if current_params and current_params[-1]:
					print "<---", line,
				current_request(current_params, usbmon_data, hid_devices[dev_address])
				current_params = None
			else:
				for command in HID_COMMANDS.keys():
					if usbmon_data.startswith(command):
						req_name = HID_COMMANDS[command]["name"]
						current_request = HID_COMMANDS[command]["request_device"]
						debug = HID_COMMANDS[command].has_key("debug") and HID_COMMANDS[command]["debug"]
						params = usbmon_data.rstrip(" <")
						params = params.split()
						params, length = params[:-1], params[-1]
						current_params = extract_bytes("".join(params)), length, debug
						if debug:
							print "--->", line,
							print "    ", req_name, dev_address, current_params
						break
				else:
					current_request = null_request
		elif URB_type == 'Ii': # Interrupt
			if event_type == 'C': # data from device
				interrupt(timestamp, status, usbmon_data, hid_devices[dev_address])

	return hid_devices

def get_rdesc(device, index):
	length, rdesc = device.rdesc[index]
	missing_chars = length - len(rdesc)
	rdesc.extend( ("**",) * missing_chars)
	return "R: " + str(length) + " " + " ".join(rdesc)

def get_description(device, index):
	desc = "# " + device.id + ":" + str(index) + " -> "
	if device.idVendor and device.idProduct:
		desc += device.idVendor + ":" + device.idProduct
		if isinstance(device.iManufacturer, str):
			desc += " / " + device.iManufacturer
		if isinstance(device.iProduct, str):
			desc += " | " + device.iProduct
	return desc

def get_devinfo(device):
	if device.idVendor and device.idProduct:
		return "I: {0} {1} {2}".format(device.bus, device.idVendor, device.idProduct)
	return None

def get_event(device, index, num):
	ts, length, data = device.incomming_data[index][num]
	if not device.init_timestamps.has_key(index):
		device.init_timestamps[index] = long(ts)
	ts = long(ts) - device.init_timestamps[index]
	return "E: {0:.06f} {1} {2}".format(ts / 1000000.0, length, data)

def print_hid_replay_dev(device, index):
	if device.rdesc.has_key(index):
		print get_rdesc(device, index)
	print get_description(device, index)
	print get_devinfo(device)
	if device.incomming_data.has_key(index):
		for num in xrange(len(device.incomming_data[index])):
			print get_event(device, index, num)
	print ""
	#print tag, timestamp, event_type, address, status, usbmon_data

def print_hid_replay(hid_devices, vendorID = None, productID = None):
	if vendorID:
		try:
			vendorID = vendorID.upper()
		except:
			vendorID = "%04X"%vendorID
	if productID:
		try:
			productID = productID.upper()
		except:
			productID = "%04X"%productID
	for dev in hid_devices.values():
		if (vendorID  != None and vendorID  != dev.idVendor) or \
		   (productID != None and productID != dev.idProduct):
			continue
		if dev.id == "001":
			#ignore hub
			continue
		dev_indexes = dev.rdesc.keys()
		for i in dev.incomming_data.keys():
			if not i in dev_indexes:
				dev_indexes.append(i)
		dev_indexes.sort()
		for i in dev_indexes:
			print_hid_replay_dev(dev, i)

def main():
	f = sys.stdin
	if len(sys.argv) > 1:
		global nomem
		f = open(sys.argv[1])
		nomem = False
	devs = usbmon2hid_replay(f)
	if not nomem:
#		print_hid_replay(devs, vendorID = 0x056a)
		print_hid_replay(devs, vendorID = None)
	f.close()

if __name__ == "__main__":
	main()
