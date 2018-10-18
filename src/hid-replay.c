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
#include <signal.h>
#include <poll.h>

/* C */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <errno.h>
#include <ccan/list/list.h>

#define _GNU_SOURCE
#include <errno.h>
#ifdef __UCLIBC__
extern const char *program_invocation_name;
extern const char *program_invocation_short_name;
#else
extern char *program_invocation_name;
extern char *program_invocation_short_name;
#endif

#define UHID_NODE	"/dev/uhid"
__u8 rdesc_buf[4096];

#define HID_REPLAY_MASK_NAME		1 << 0
#define HID_REPLAY_MASK_RDESC		1 << 1
#define HID_REPLAY_MASK_INFO		1 << 2
#define HID_REPLAY_MASK_COMPLETE	(HID_REPLAY_MASK_NAME | \
					 HID_REPLAY_MASK_RDESC | \
					 HID_REPLAY_MASK_INFO)

struct hid_replay_device {
	int fuhid;
	int idx;
	struct list_node list;
};

struct hid_replay_devices_list {
	struct list_head devices;
	struct hid_replay_device *current;
	struct pollfd *fds;
	int count;
};

/* global because used in the signal handler */
static struct hid_replay_devices_list *devices;
static FILE *fp;

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

static int hid_replay_switch_dev(char *rdesc, ssize_t len)
{
	int i;
	int n = sscanf(rdesc, "D: %d\n", &i);
	if (n != 1)
		return -1;
	return i;
}

static void hid_replay_incoming_event(int fd, struct uhid_event *r_event)
{
	struct uhid_event w_event = { 0 };

	switch (r_event->type) {
	case UHID_GET_REPORT:
		w_event.type = UHID_GET_REPORT_REPLY;
		w_event.u.get_report_reply.id = r_event->u.get_report.id;
		w_event.u.get_report_reply.err = -EIO;
		w_event.u.get_report_reply.size = 0;
		write(fd, &w_event, sizeof(w_event));
		break;
	case UHID_SET_REPORT:
		w_event.type = UHID_SET_REPORT_REPLY;
		w_event.u.set_report_reply.id = r_event->u.get_report.id;
		w_event.u.set_report_reply.err = -EIO;
		write(fd, &w_event, sizeof(w_event));
		break;
	case UHID_START:
	case UHID_STOP:
	case UHID_OPEN:
	case UHID_CLOSE:
	case UHID_OUTPUT:
	case __UHID_LEGACY_OUTPUT_EV:
	case __UHID_LEGACY_INPUT:
	case UHID_INPUT2:
		/* do nothing */
		break;
	default:
		fprintf(stderr,
			"received unknown uhid event %d\n",
			r_event->type);
	}
}

static int hid_replay_get_one_event(struct hid_replay_devices_list *devices,
				     struct uhid_event *event,
				     int timeout)
{
	int i, ret;

	do {
		ret = poll(devices->fds, devices->count, timeout);

		if (ret > 0 && devices->fds[0].revents & POLLIN)
			ret--; /* ignore stdin inputs */

		if (ret == 0)
			return 0; /* timeout */

		if (ret > 0) {
			for (i=1; i < devices->count; i++) {
				if (devices->fds[i].revents & POLLIN) {
					read(devices->fds[i].fd, event, sizeof(*event));
					hid_replay_incoming_event(devices->fds[i].fd,
								  event);
					return 1;
				}
			}
		}
	} while (ret > 0);

	return ret;
}

static void hid_replay_sleep(struct hid_replay_devices_list *devices,
			     long timeout_usec)
{
	struct uhid_event event;
	struct timeval current_time, end_time;
	long current_timeout;

	if (timeout_usec < 1000) {
		usleep(timeout_usec);
		return;
	}

	gettimeofday(&end_time, NULL);

	end_time.tv_usec += timeout_usec;
	end_time.tv_sec += timeout_usec / 1000000L;

	/* we need to flush the incoming events until timeout is done */
	do {
		gettimeofday(&current_time, NULL);
		current_timeout = (end_time.tv_sec - current_time.tv_sec) * 1000000L;
		current_timeout += end_time.tv_usec - current_time.tv_usec;
		if (current_timeout / 1000 > 0) {
			hid_replay_get_one_event(devices, &event, current_timeout / 1000);
		} else if (current_timeout > 0) {
			usleep(current_timeout);
		}
	} while (current_timeout > 0);
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
		hid_replay_sleep(devices, usec);

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
	if (len - 3 >= (ssize_t)sizeof(dev->name))
		return;
	sscanf(buf, "N: %[^\n]\n", dev->name);
	len = strlen((const char *)dev->name);
	if (dev->name[len - 1] == '\r')
		dev->name[len - 1] = '\0';
}

static void hid_replay_phys(char *buf, ssize_t len, struct uhid_create_req *dev)
{
	if (len - 3 >= (ssize_t)sizeof(dev->phys))
		return;
	sscanf(buf, "P: %[^\n]\n", dev->phys);
}

static void hid_replay_info(char *buf, ssize_t len, struct uhid_create_req *dev)
{
	int bus;
	int vid;
	int pid;
	int n;
	if (len - 3 >= (ssize_t)sizeof(dev->phys))
		return;
	n = sscanf(buf, "I: %x %x %x\n", &bus, &vid, &pid);
	if (n != 3)
		return;

	dev->bus = bus;
	dev->vendor = vid;
	dev->product = pid;
}

static void hid_replay_destroy_device(struct hid_replay_device *device)
{
	if (device->fuhid)
		close(device->fuhid);
	free(device);
}

static void hid_replay_destroy_devices(struct hid_replay_devices_list *devices)
{
	struct hid_replay_device *device, *next;

	list_for_each_safe(&devices->devices, device, next, list) {
		list_del(&device->list);
		hid_replay_destroy_device(device);
	}
	free(devices);
}

static int hid_replay_parse_header(FILE *fp, struct uhid_create_req *dev)
{
	unsigned int mask = 0;
	char *buf = 0;
	int stop = 0;
	ssize_t size;
	size_t n;
	int device_index = 0;

	do {
		size = getline(&buf, &n, fp);
		if (size == -1)
			continue;

		switch (buf[0]) {
			case '#':
				/* comments, just skip the line */
				break;
			case 'D':
				if (mask == 0) {
					if (device_index == 0)
						device_index = hid_replay_switch_dev(buf, size);
				} else {
					fprintf(stderr, "Error while parsing hid-replay file, got a Device switch while the previous device was not fully configured.\n");
					return -1;
				}
				break;
			case 'R':
				hid_replay_rdesc(buf, size, dev);
				mask |= HID_REPLAY_MASK_RDESC;
				break;
			case 'N':
				hid_replay_name(buf, size, dev);
				mask |= HID_REPLAY_MASK_NAME;
				break;
			case 'P':
				hid_replay_phys(buf, size, dev);
				break;
			case 'I':
				hid_replay_info(buf, size, dev);
				mask |= HID_REPLAY_MASK_INFO;
				break;
		}

		if (mask == HID_REPLAY_MASK_COMPLETE) {
			stop = 1;
		}

	} while (size > 0 && !stop);

	free(buf);

	if (mask != HID_REPLAY_MASK_COMPLETE)
		return -1;

	return device_index;
}

static struct hid_replay_device *__hid_replay_create_device(int idx, struct uhid_create_req *dev)
{
	struct uhid_event event;
	struct hid_replay_device *device;

	device = calloc(1, sizeof(struct hid_replay_device));
	if (device == NULL) {
		fprintf(stderr, "Failed to allocate uHID device: %s\n", strerror(errno));
		return NULL;
	}

	device->idx = idx;
	device->fuhid = open(UHID_NODE, O_RDWR);
	if (device->fuhid < 0){
		fprintf(stderr, "Failed to open uHID node: %s\n", strerror(errno));
		free(device);
		return NULL;
	}

	memset(&event, 0, sizeof(event));
	event.type = UHID_CREATE;
	event.u.create = *dev;

	if (write(device->fuhid, &event, sizeof(event)) < 0) {
		fprintf(stderr, "Failed to create uHID device: %s\n", strerror(errno));
		hid_replay_destroy_device(device);
	}

	return device;
}



static struct hid_replay_devices_list *hid_replay_create_devices(FILE *fp)
{
	struct uhid_create_req dev;
	struct hid_replay_devices_list *list = calloc(1, sizeof(struct hid_replay_devices_list));
	int idx;

	if (!list)
		return NULL;

	list_head_init(&list->devices);

	do {
		memset(&dev, 0, sizeof(dev));
		idx = hid_replay_parse_header(fp, &dev);
		if (idx >= 0) {
			struct hid_replay_device *new_dev = __hid_replay_create_device(idx, &dev);
			if (!new_dev)
				continue;

			list_add(&list->devices, &new_dev->list);
			list->current = new_dev;
		}
	} while (idx >= 0);

	return list;
}

static int hid_replay_setup_pollfd(struct hid_replay_devices_list *devices)
{
	struct pollfd *fds;
	struct hid_replay_device *device;
	int count = 1; /* stdin */

	list_for_each(&devices->devices, device, list)
		++count;

	fds = calloc(count, sizeof(struct pollfd));
	if (!fds)
		return -ENOMEM;

	fds[0].fd = STDIN_FILENO;
	fds[0].events = POLLIN;
	count = 1;

	list_for_each(&devices->devices, device, list) {
		fds[count].fd = device->fuhid;
		fds[count].events = POLLIN;
		++count;
	}

	devices->fds = fds;
	devices->count = count;

	return 0;
}

static int hid_replay_wait_opened(struct hid_replay_devices_list *devices)
{
	int i, ret;
	struct uhid_event event;

	do {
		ret = hid_replay_get_one_event(devices, &event, -1);
		if (ret == 1) {
			if (event.type == UHID_OPEN) {
				return 0;
			}
		}
	} while (ret == 1);

	return 0;
}

static int hid_replay_read_one(FILE *fp, struct hid_replay_devices_list *devices, struct timeval *time)
{
	char *buf = 0;
	ssize_t size;
	size_t n;
	int new_id;
	struct hid_replay_device *device;

	do {
		size = getline(&buf, &n, fp);
		if (size < 1)
			break;
		switch (buf[0]) {
		case 'E':
			hid_replay_event(devices->current->fuhid, buf, size, time);
			free(buf);
			return 0;
		case 'D':
			new_id = hid_replay_switch_dev(buf, size);
			list_for_each(&devices->devices, device, list)
				if (device->idx == new_id)
					devices->current = device;
		}
	} while (1);

	free(buf);

	return 1;
}

static int try_open_uhid()
{
	int fuhid = open(UHID_NODE, O_RDWR);
	if (fuhid < 0){
		fprintf(stderr, "Failed to open uHID node: %s\n", strerror(errno));
		return 1;
	}

	close(fuhid);

	return 0;
}

static void signal_callback_handler(int signum)
{
	free(devices->fds);
	fclose(fp);
	hid_replay_destroy_devices(devices);

	/* Terminate program */
	exit(signum);
}

int main(int argc, char **argv)
{
	struct uhid_event event;
	struct uhid_create_req dev;
	struct timeval time;
	int stop = 0;
	char line[40];
	char *hid_file;
	enum hid_replay_mode mode = MODE_INTERACTIVE;
	int sleep_time = 0;
	int error;

	memset(&event, 0, sizeof(event));
	memset(&dev, 0, sizeof(dev));

	if (try_open_uhid())
		return EXIT_FAILURE;

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

	devices = hid_replay_create_devices(fp);

	if (!devices)
		return EXIT_FAILURE;

	error = hid_replay_setup_pollfd(devices);
	if (error)
		return error;

	hid_replay_wait_opened(devices);

	if (sleep_time)
		hid_replay_sleep(devices, sleep_time * 1000000);

	signal(SIGINT, signal_callback_handler);

	stop = 0;
	while (!stop) {
		if (mode == MODE_INTERACTIVE) {
			printf("Hit enter (re)start replaying the events\n");
			do {
				hid_replay_get_one_event(devices, &event, -1);
			} while (!devices->fds[0].revents & POLLIN);
			fgets (line, sizeof(line), stdin);
		} else
			stop = 1;

		memset(&time, 0, sizeof(time));
		fseek(fp, 0, SEEK_SET);
		do {
			error = hid_replay_read_one(fp, devices, &time);
		} while (!error);
	}

	free(devices->fds);
	fclose(fp);
	hid_replay_destroy_devices(devices);
	return 0;
}
