#!/bin/env python
# -*- coding: utf-8 -*-
#
#	report.py, a multitouch diagnostic reporter
#
#	The copyright owners for the contents of this file are:
#		Ecole Nationale de l'Aviation Civile, France (2010-2011)
#		Red Hat, Inc. (2012)
#
#	Contributors:
#		Benjamin Tissoires <benjamin.tissoires@gmail.com>
#
#
#	This program is provided to you as free software;
#	you can redistribute it	and/or modify it under the terms of the
#	GNU General Public License as published by the Free Software
#	Foundation; either version 2 of the License, or (at your option)
#	any later version.

import os
import sys
import re

# first, check the user id
if int(os.popen("id -u").read()) != 0:
	print "Must be run with root privileges"
	sys.exit(1)

# then, disable stdout buffering
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

# get the kernel version
cmd = "uname -a"
print cmd
print os.popen(cmd).read()

# get the report descriptors through lsusb first.

os.chdir("/sys/bus/usb/drivers/usbhid")

USB_PATH = []
USB = []

for file in os.listdir("."):
	m = re.match(r".*\:.*", file)
	if not m:
		continue
	# we now have only the links to the devices

	uevent = ""
	name = ""
	usb = ""
	# find the name and path of the device
	for subfile in os.listdir(file):
		m = re.match(r"\d*\:.*", subfile)
		if not m:
			continue
		uevent = file + "/" + subfile + "/uevent"

	uevent_f = open(uevent,'r')
	for l in uevent_f:
		m = re.match(r"(HID_ID|HID_NAME)=(.*)",l)
		if m:
			var, value = m.groups()
			if var == "HID_NAME":
				name = value
			elif var == "HID_ID":
				usb = ":".join(value.split(":")[1:])

	if usb not in USB:
		print "found device", name
		USB.append(usb)

	USB_PATH.append(file)
	cmd = "echo " + file + " > unbind"
	print cmd
	os.popen(cmd)

for usb in USB:
	cmd = "lsusb -v -d " + usb
	print cmd
	print os.popen(cmd).read()

for file in USB_PATH:
	cmd = "echo " + file + " > bind"
	print cmd
	os.popen(cmd)

# now work with hidraw
import fcntl
import struct
import array
import os
import glob
import sys
import select
from datetime import datetime

def ioctl(fd, EVIOC, code, return_type, buf = None):
	size = struct.calcsize(return_type)
	if buf == None:
		buf = size*'\x00'
	abs = fcntl.ioctl(fd, EVIOC(code, size), buf)
	return struct.unpack(return_type, abs)

# extracted from <asm-generic/ioctl.h>
_IOC_WRITE = 1
_IOC_READ = 2

_IOC_NRBITS = 8
_IOC_TYPEBITS = 8
_IOC_SIZEBITS = 14
_IOC_DIRBITS = 2

_IOC_NRSHIFT = 0
_IOC_TYPESHIFT = _IOC_NRSHIFT + _IOC_NRBITS
_IOC_SIZESHIFT = _IOC_TYPESHIFT + _IOC_TYPEBITS
_IOC_DIRSHIFT = _IOC_SIZESHIFT + _IOC_SIZEBITS

#define _IOC(dir,type,nr,size) \
#	(((dir)  << _IOC_DIRSHIFT) | \
#	 ((type) << _IOC_TYPESHIFT) | \
#	 ((nr)   << _IOC_NRSHIFT) | \
#	 ((size) << _IOC_SIZESHIFT))
def _IOC(dir, type, nr, size):
        return ( (dir << _IOC_DIRSHIFT) |
                 (ord(type) << _IOC_TYPESHIFT) |
                 (nr << _IOC_NRSHIFT) |
                 (size << _IOC_SIZESHIFT))

#define _IOR(type,nr,size)	_IOC(_IOC_READ,(type),(nr),(_IOC_TYPECHECK(size)))
def _IOR(type,nr,size):
	return _IOC(_IOC_READ, type, nr, size)

#define _IOW(type,nr,size)	_IOC(_IOC_WRITE,(type),(nr),(_IOC_TYPECHECK(size)))
def _IOW(type,nr,size):
	return _IOC(_IOC_WRITE, type, nr, size)


#define HIDIOCGRDESCSIZE	_IOR('H', 0x01, int)
def _HIDIOCGRDESCSIZE(none, len):
	return _IOR('H', 0x01, len)

def HIDIOCGRDESCSIZE(fd):
	""" get report descriptors size """
	type = 'i'
	return int(*ioctl(fd, _HIDIOCGRDESCSIZE, None, type))

#define HIDIOCGRDESC		_IOR('H', 0x02, struct hidraw_report_descriptor)
def _HIDIOCGRDESC(none, len):
	return _IOR('H', 0x02, len)

def HIDIOCGRDESC(fd, size):
	""" get report descriptors """
	format = "I4096c"
	value = '\0'*4096
	tmp = struct.pack("i", size) + value[:4096].ljust(4096, '\0')
	_buffer = array.array('B', tmp)
	fcntl.ioctl(fd, _HIDIOCGRDESC(None, struct.calcsize(format)), _buffer)
	size, = struct.unpack("i", _buffer[:4])
	value = _buffer[4:size+4]
	return size, value

#define HIDIOCGRAWINFO		_IOR('H', 0x03, struct hidraw_devinfo)
def _HIDIOCGRAWINFO(none, len):
	return _IOR('H', 0x03, len)

def HIDIOCGRAWINFO(fd):
	""" get hidraw device infos """
	type = 'ihh'
	return ioctl(fd, _HIDIOCGRAWINFO, None, type)

#define HIDIOCGRAWNAME(len)     _IOC(_IOC_READ, 'H', 0x04, len)
def _HIDIOCGRAWNAME(none, len):
	return _IOC(_IOC_READ, 'H', 0x04, len)

def HIDIOCGRAWNAME(fd):
	""" get device name """
	type = 1024*'c'
	return "".join(ioctl(fd, _HIDIOCGRAWNAME, None, type)).rstrip('\x00')

instructions = (
	"1. Drag _one_ finger on the screen from one corner to the opposite, and release it.",
	"""2. Land one finger,
   - land a second finger far enough from the first
   - move your two fingers
   - release the *first* finger
   - release the second finger""",
	"3. Finally, move your ten fingers on the screen and release them.",
	"Thank you.",
)

def trace(device):
	file = os.open(device, os.O_RDONLY)
	size = HIDIOCGRDESCSIZE(file)
	rsize, rdesc = HIDIOCGRDESC(file, size)
	if size != rsize:
		print "error, got", rsize, "instead of", size
		return
	rdesc_str = ["%02x" % (data) for data in rdesc]
	bus, vid, pid = HIDIOCGRAWINFO(file)
	name = HIDIOCGRAWNAME(file)
	sys.stderr.write("Opening "+name+" ("+device+")\n")
	print "R:", size, " ".join(rdesc_str)
	print "N:", name
	print "I:", bus, "%04x %04x" % (vid,pid)
	starttime = None
	instr = 0
	sys.stderr.write("Please follow these "+str(len(instructions) - 1)+" steps:\n")
	sys.stderr.write(instructions[instr] + "\n")
	print "# " + instructions[instr]
	instr += 1
	capture = True
	events = False
	while capture:
		ready,_,_ = select.select([file],[],[], 2)
		if not ready:
			if events:
				sys.stderr.write(instructions[instr] + "\n")
				print "# " + instructions[instr]
				events = False
				instr += 1
				capture = instr < len(instructions)
			continue
		rdata = os.read(file, 4096)
		events = True
		now = datetime.now()
		if not starttime:
			starttime = now
		delta = now - starttime
		fmt = 'B'*len(rdata)
		data = struct.unpack(fmt, rdata)
		data = ["%02x" % (d) for d in data]
		print "E:", "%d.%06d" % (delta.seconds, delta.microseconds), len(rdata), " ".join(data)
	os.close(file)

def find_device():
	filename = ""
	files = glob.glob('/dev/hidraw*')
	files.sort()
	for hidfile in files:
		file = os.open(hidfile, os.O_RDONLY)
		name = HIDIOCGRAWNAME(file)
		os.close(file)
		sys.stderr.write(hidfile +": "+name+"\n")
		print hidfile, name
	sys.stderr.write("Select the device event number [0-%d]: " % (len(files) - 1))
	l = sys.stdin.readline()
	print int(l)
	return "/dev/hidraw"+str(int(l))

sys.stderr.write("These are the available hidraw devices so far:\n")
trace(find_device())
