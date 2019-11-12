HID replay - HID recorder

This program allow users to capture hidraw events and then
replay them through the uhid kernel module.

In order to replay the HID events, you will need to load the
module uhid which is available in kernels v3.6+.

More documentation is available at
http://bentiss.github.io/hid-replay-docs/

This is mainly for debugging kernel drivers. If your goal
is just to replay events, have a look at evemu:
http://wiki.freedesktop.org/wiki/Evemu

