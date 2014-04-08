#!/bin/env python

import parse_rdesc
import sys
import struct

output = open("out.bin", "wb")

def dump_rdesc(data, prefix, dst):
	if len(prefix) > 1:
		raise Exception, "Invalid prefix: %s"%prefix
	rdesc = parse_rdesc.parse_rdesc(data, None)
	if not rdesc:
		raise IOError
	dst.write(struct.pack('c', prefix))
	dst.write(struct.pack('i', rdesc.size()))
	for b in rdesc.data():
		dst.write(struct.pack('B', b))

for filename in sys.argv[1:]:
	f = open(filename)
	for line in f.readlines():
		if line.startswith("R:"):
			dump_rdesc(line.lstrip("R: "), "R", output)
		elif line.startswith("O:"):
			dump_rdesc(line.lstrip("O: "), "O", output)

output.close()
