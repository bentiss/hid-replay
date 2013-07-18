/*
 * Hid replay
 *
 * Copyright (c) 2012 Benjamin Tissoires <benjamin.tissoires@gmail.com>
 * Copyright (c) 2012 Red Hat, Inc.
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

#if HAVE_CONFIG_H
#include <config.h>
#endif

/* Linux */
#include <linux/types.h>
#include <linux/input.h>
#include <linux/uhid.h>

/* Unix */
#include <sys/ioctl.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <getopt.h>

/* C */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <errno.h>

#define _GNU_SOURCE
#include <errno.h>
extern char *program_invocation_name;
extern char *program_invocation_short_name;

#define UHID_NODE	"/dev/uhid"
__u8 rdesc_buf[4096];

#define HID_REPLAY_MASK_NAME		1 << 0
#define HID_REPLAY_MASK_RDESC		1 << 1
#define HID_REPLAY_MASK_INFO		1 << 2
#define HID_REPLAY_MASK_COMPLETE	(HID_REPLAY_MASK_NAME | \
					 HID_REPLAY_MASK_RDESC | \
					 HID_REPLAY_MASK_INFO)

/**
 * Print usage information.
 */
static int usage(void)
{
	printf("USAGE:\n");
	printf("   %s [OPTION] filename\n", program_invocation_short_name);

	printf("\n");
	printf("where OPTION is either:\n");
	printf("   -h or --help: print this message\n");
	printf("   -i or --interactive: default mode: interactive mode (allow to control and to replay several times)\n");
	printf("   -1 or --one: play once the events without waiting and then exit\n");
	printf("   -s X or --sleep X: sleep X seconds once the device is created before next step\n");

	return EXIT_FAILURE;
}

enum hid_replay_mode {
	MODE_AUTO,
	MODE_INTERACTIVE,
};

static const struct option long_options[] = {
	{ "help", no_argument, NULL, 'h' },
	{ "sleep", required_argument, NULL, 's' },
	{ "one", no_argument, NULL, '1' },
	{ "interactive", no_argument, NULL, 'i' },
	{ 0, },
};

static void hid_replay_rdesc(char *rdesc, ssize_t len, struct uhid_create_req *dev)
{
	int rdesc_len, i;
	int n = sscanf(rdesc, "R: %d %[^\n]\n", &rdesc_len, rdesc);
	if (n != 2)
		return;
	/* TODO: check consistency of rdesc */
	for (i = 0; i < rdesc_len; ++i) {
		n = sscanf(rdesc, "%hhx %[^\n]\n", &rdesc_buf[i], rdesc);
		if (n != 2) {
			if ((i == rdesc_len - 1) && n == 1)
				break;
			return;
		}
	}
	dev->rd_data = rdesc_buf;
	dev->rd_size = rdesc_len;
}

static void hid_replay_event(int fuhid, char *ubuf, ssize_t len, struct timeval *time)
{
	struct uhid_event ev;
	struct uhid_input_req *input = &ev.u.input;
	int event_len, i;
	struct timeval ev_time;
	unsigned long sec;
	unsigned usec;
	char *buf = ubuf;
	int n = sscanf(buf, "E: %lu.%06u %d %[^\n]\n", &sec, &usec, &event_len, buf);
	if (n != 4)
		return;
	/* TODO: check consistency of buf */

	memset(&ev, 0, sizeof(ev));
	ev.type = UHID_INPUT;
	ev_time.tv_sec = sec;
	ev_time.tv_usec = usec;

	if (time->tv_sec == 0 && time->tv_usec == 0)
		*time = ev_time;

	usec = 1000000L * (ev_time.tv_sec - time->tv_sec);
	usec += ev_time.tv_usec - time->tv_usec;

	if (usec > 500) {
		if (usec > 3000000)
			usec = 3000000;
		usleep(usec);
		*time = ev_time;
	}

	for (i = 0; i < event_len; ++i) {
		n = sscanf(buf, "%hhx %[^\n]\n", &input->data[i], buf);
		if (n != 2) {
			if ((i == event_len - 1) && n == 1)
				break;
			return;
		}
	}

	input->size = event_len;

	if (write(fuhid, &ev, sizeof(ev)) < 0)
		fprintf(stderr, "Failed to write uHID event: %s\n", strerror(errno));
}

static void hid_replay_name(char *buf, ssize_t len, struct uhid_create_req *dev)
{
	if (len - 3 >= sizeof(dev->name))
		return;
	sscanf(buf, "N: %[^\n]\n", dev->name);
	len = strlen(dev->name);
	if (dev->name[len - 1] == '\r')
		dev->name[len - 1] = '\0';
}

static void hid_replay_phys(char *buf, ssize_t len, struct uhid_create_req *dev)
{
	if (len - 3 >= sizeof(dev->phys))
		return;
	sscanf(buf, "P: %[^\n]\n", dev->phys);
}

static void hid_replay_info(char *buf, ssize_t len, struct uhid_create_req *dev)
{
	int bus;
	int vid;
	int pid;
	int n;
	if (len - 3 >= sizeof(dev->phys))
		return;
	n = sscanf(buf, "I: %x %x %x\n", &bus, &vid, &pid);
	if (n != 3)
		return;

	dev->bus = bus;
	dev->vendor = vid;
	dev->product = pid;
}

static void hid_replay_create_device(int fuhid, struct uhid_create_req *dev)
{
	struct uhid_event event;

	memset(&event, 0, sizeof(event));
	event.type = UHID_CREATE;
	event.u.create = *dev;

	if (write(fuhid, &event, sizeof(event)) < 0)
		fprintf(stderr, "Failed to create uHID device: %s\n", strerror(errno));
}


int main(int argc, char **argv)
{
	FILE *fp;
	int fuhid = open(UHID_NODE, O_RDWR);
	struct uhid_event event;
	struct uhid_create_req dev;
	char *buf = 0;
	ssize_t size;
	size_t n;
	int stop = 0;
	struct timeval time;
	long event_pos;
	char line[40];
	char *hid_file;
	enum hid_replay_mode mode = MODE_INTERACTIVE;
	int sleep_time = 0;
	unsigned int mask = 0;

	memset(&event, 0, sizeof(event));
	memset(&dev, 0, sizeof(dev));

	if (fuhid < 0){
		fprintf(stderr, "Failed to open uHID node: %s\n", strerror(errno));
		return EXIT_FAILURE;
	}

	while (1) {
		int option_index = 0;
		int c = getopt_long(argc, argv, "hi1s:", long_options, &option_index);
		if (c == -1)
			break;
		switch (c) {
		case '1':
			mode = MODE_AUTO;
			break;
		case 'i':
			mode = MODE_INTERACTIVE;
			break;
		case 's':
			sleep_time = atoi(optarg);
			break;
		default:
			return usage();
		}
	}

	if (optind < argc) {
		hid_file = argv[optind++];
		fp = fopen(hid_file, "r");
	} else
		fp = stdin;

	if (!fp) {
		fprintf(stderr, "Failed to open %s: %s\n", hid_file, strerror(errno));
		return usage();
	}

	do {
		size = getline(&buf, &n, fp);
		switch (buf[0]) {
			case '#':
				/* comments, just skip the line */
				break;
			case 'R':
				hid_replay_rdesc(buf, size, &dev);
				mask |= HID_REPLAY_MASK_RDESC;
				break;
			case 'N':
				hid_replay_name(buf, size, &dev);
				mask |= HID_REPLAY_MASK_NAME;
				break;
			case 'P':
				hid_replay_phys(buf, size, &dev);
				break;
			case 'I':
				hid_replay_info(buf, size, &dev);
				mask |= HID_REPLAY_MASK_INFO;
				break;
		}

		if (mask == HID_REPLAY_MASK_COMPLETE) {
			event_pos = ftell(fp);
			hid_replay_create_device(fuhid, &dev);
			stop = 1;
		}

	} while (size > 0 && !stop);

	stop = 0;

	while (!stop) {
		read(fuhid, &event, sizeof(event));
		stop = event.type == UHID_OPEN;
	}

	if (sleep_time)
		sleep(sleep_time);

	stop = 0;
	while (!stop) {
		if (mode == MODE_INTERACTIVE) {
			printf("Hit enter (re)start replaying the events\n");
			fgets (line, sizeof(line), stdin);
		} else
			stop = 1;

		memset(&time, 0, sizeof(time));
		fseek(fp, event_pos, SEEK_SET);
		do {
			size = getline(&buf, &n, fp);
			if (buf[0] == 'E') {
				hid_replay_event(fuhid, buf, size, &time);
			}
		} while (size > 0);
	}

	fclose(fp);
	close(fuhid);
	free(buf);
	return 0;
}
