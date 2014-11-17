/*
 * Hid replay / recorder
 *
 * Copyright (c) 2012 Benjamin Tissoires <benjamin.tissoires@gmail.com>
 * Copyright (c) 2012 Red Hat, Inc.
 *
 * Based on: "Hidraw Userspace Example" copyrighted as this:
 *   Copyright (c) 2010 Alan Ott <alan@signal11.us>
 *   Copyright (c) 2010 Signal 11 Software
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

#define _GNU_SOURCE

/* Linux */
#include <linux/types.h>
#include <linux/input.h>
#include <linux/hidraw.h>

/* Unix */
#include <sys/ioctl.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <fcntl.h>
#include <unistd.h>
#include <getopt.h>
#include <dirent.h>
#include <signal.h>
#include <poll.h>

/* C */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#define _GNU_SOURCE
#include <errno.h>
extern char *program_invocation_name;
extern char *program_invocation_short_name;

#define DEV_DIR "/dev"
#define HIDRAW_DEV_NAME "hidraw"

#define HID_DBG_DIR "/sys/kernel/debug/hid"
#define HID_DBG_RDESC "rdesc"
#define HID_DBG_events "events"

enum hid_recorder_mode {
	MODE_HIDRAW,
	MODE_HID_DEBUGFS,
};

struct hid_recorder_device {
	int fd;
	int idx;
	FILE *hid_dbg_file;
	char *filename;
	struct hidraw_report_descriptor rpt_desc;
	struct hidraw_devinfo info;
	char name[256];
	char phys[256];
	enum hid_recorder_mode mode;
	char *buf_read;
	char *buf_write;
	size_t buf_size;
};

struct hid_recorder_state {
	enum hid_recorder_mode mode;
	struct pollfd *fds;
	struct hid_recorder_device *devices;
	struct hid_recorder_device *current;
	struct timeval starttime;
	int device_count;
	int event_count;
};

/* global because used in signal handler */
static struct hid_recorder_state state = {0};

/**
 * Print usage information.
 */
static int usage(void)
{
	printf("USAGE:\n");
	printf("   %s [OPTION] [/dev/hidrawX] [[/dev/hidrawY] ... ]\n", program_invocation_short_name);

	printf("\n");
	printf("where OPTION is either:\n");
	printf("   -h or --help: print this message\n");
	printf("   -d or --debugfs: use HID debugfs instead of hidraw node (use this when\n"
		"                    no events are coming from hidraw while using the device)\n");
	printf("\n");
	printf("Note that you can pass several hidraw device nodes at once.\n");
	return EXIT_FAILURE;
}

static const struct option long_options[] = {
	{ "help", no_argument, NULL, 'h' },
	{ "debugfs", no_argument, NULL, 'd' },
	{ 0, },
};

/* Return 1 if the difference is negative, otherwise 0.  */
int timeval_subtract(struct timeval *result, struct timeval *t2, struct timeval *t1)
{
	long int diff = (t2->tv_usec + 1000000 * t2->tv_sec) - (t1->tv_usec + 1000000 * t1->tv_sec);
	result->tv_sec = diff / 1000000;
	result->tv_usec = diff % 1000000;

	return (diff < 0);
}

/**
 * Filter for the AutoDevProbe scandir on /dev.
 *
 * @param dir The current directory entry provided by scandir.
 *
 * @return Non-zero if the given directory entry starts with "hidraw", or zero
 * otherwise.
 */
static int is_hidraw_device(const struct dirent *dir) {
	return strncmp(HIDRAW_DEV_NAME, dir->d_name, 6) == 0;
}

/**
 * Scans all /dev/hidraw*, display them and ask the user which one to
 * open.
 *
 * code taken from evtest.c
 *
 * @return The hidraw device file name of the device file selected. This
 * string is allocated and must be freed by the caller.
 */
static char* scan_devices(void)
{
	struct dirent **namelist;
	int i, ndev, devnum, res;
	char *filename;

	ndev = scandir(DEV_DIR, &namelist, is_hidraw_device, alphasort);
	if (ndev <= 0)
		return NULL;

	fprintf(stderr, "Available devices:\n");

	for (i = 0; i < ndev; i++)
	{
		char fname[64];
		int fd = -1;
		char name[256] = "???";

		snprintf(fname, sizeof(fname),
			 "%s/%s", DEV_DIR, namelist[i]->d_name);
		fd = open(fname, O_RDONLY);
		if (fd < 0) {
			free(namelist[i]);
			continue;
		}

		/* Get Raw Name */
		res = ioctl(fd, HIDIOCGRAWNAME(256), name);
		if (res >= 0)
			fprintf(stderr, "%s:	%s\n", fname, name);
		close(fd);
		free(namelist[i]);
	}

	free(namelist);

	fprintf(stderr, "Select the device event number [0-%d]: ", ndev - 1);
	scanf("%d", &devnum);

	if (devnum >= ndev || devnum < 0)
		return NULL;

	asprintf(&filename, "%s/%s%d",
		 DEV_DIR, HIDRAW_DEV_NAME,
		 devnum);

	return filename;
}

static int rdesc_match(struct hidraw_report_descriptor *rpt_desc, const char *str, int size)
{
	int i;
	int rdesc_size_str = (size - 1) / 3; /* remove terminating \0,
						2 chars per u8 + space (or \n for the last) */

	if (rdesc_size_str != rpt_desc->size)
		return 0;

	for (i = 0; i < rdesc_size_str; i++) {
		__u8 v;
		sscanf(&str[i*3], "%hhx ", &v);
		if (v != rpt_desc->value[i])
			break;
	}

	return i == rdesc_size_str;
}

static char* find_hid_dbg(struct hidraw_devinfo *info, struct hidraw_report_descriptor *rpt_desc)
{
	struct dirent **namelist;
	int i, ndev;
	char *filename = NULL;
	char target_name[16];
	char *buf_read = NULL;
	size_t buf_size = 0;

	snprintf(target_name, sizeof(target_name),
		 "%04d:%04X:%04X:", info->bustype, info->vendor, info->product);

	ndev = scandir(HID_DBG_DIR, &namelist, NULL, alphasort);
	if (ndev <= 0)
		return NULL;

	for (i = 0; i < ndev; i++)
	{
		char fname[256];
		FILE *file;
		int size;

		snprintf(fname, sizeof(fname),
			 "%s/%s/rdesc", HID_DBG_DIR, namelist[i]->d_name);
		file = fopen(fname, "r");
		if (!file) {
			free(namelist[i]);
			continue;
		}

		/* Get Report Descriptor */
		size = getline(&buf_read, &buf_size, file);
		if (rdesc_match(rpt_desc, buf_read, size)) {
			filename = malloc(256);
			snprintf(filename, 256,
				 "%s/%s/events", HID_DBG_DIR, namelist[i]->d_name);
		}
		fclose(file);
		free(namelist[i]);
	}

	free(namelist);
	free(buf_read);

	return filename;
}

static int fetch_hidraw_information(struct hid_recorder_device *device)
{
	int fd = device->fd;
	struct hidraw_report_descriptor *rpt_desc = &device->rpt_desc;
	struct hidraw_devinfo *info = &device->info;
	char *name = device->name;
	char *phys = device->phys;
	int i, res, desc_size = 0;
	memset(rpt_desc, 0x0, sizeof(*rpt_desc));
	memset(info, 0x0, sizeof(*info));
	memset(name, 0x0, 256);
	memset(phys, 0x0, 256);

	printf("D: %d\n", device->idx);

	/* Get Report Descriptor Size */
	res = ioctl(fd, HIDIOCGRDESCSIZE, &desc_size);
	if (res < 0) {
		perror("HIDIOCGRDESCSIZE");
		return EXIT_FAILURE;
	}

	/* Get Report Descriptor */
	rpt_desc->size = desc_size;
	res = ioctl(fd, HIDIOCGRDESC, rpt_desc);
	if (res < 0) {
		perror("HIDIOCGRDESC");
		return EXIT_FAILURE;
	} else {
		printf("R: %d", desc_size);
		for (i = 0; i < rpt_desc->size; i++)
			printf(" %02hhx", rpt_desc->value[i]);
		printf("\n");
	}

	/* Get Raw Name */
	res = ioctl(fd, HIDIOCGRAWNAME(256), name);
	if (res < 0) {
		perror("HIDIOCGRAWNAME");
		return EXIT_FAILURE;
	} else
		printf("N: %s\n", name);

	/* Get Physical Location */
	res = ioctl(fd, HIDIOCGRAWPHYS(256), phys);
	if (res < 0) {
		perror("HIDIOCGRAWPHYS");
		return EXIT_FAILURE;
	} else
		printf("P: %s\n", phys);

	/* Get Raw Info */
	res = ioctl(fd, HIDIOCGRAWINFO, info);
	if (res < 0) {
		perror("HIDIOCGRAWINFO");
		return EXIT_FAILURE;
	} else {
		printf("I: %x %04hx %04hx\n", info->bustype, info->vendor, info->product);
	}

	fflush(stdout);

	return EXIT_SUCCESS;
}

static void print_currenttime(struct timeval *starttime)
{
	struct timeval currenttime;
	if (!starttime->tv_sec && !starttime->tv_usec)
		gettimeofday(starttime, NULL);
	gettimeofday(&currenttime, NULL);
	timeval_subtract(&currenttime, &currenttime, starttime);

	printf("%lu.%06u", currenttime.tv_sec, (unsigned)currenttime.tv_usec);
}

static int read_hiddbg_event(struct hid_recorder_device *device)
{
	int size;
	FILE *file = device->hid_dbg_file;
	struct timeval *starttime = &state.starttime;
	char **buf_read = &device->buf_read;
	char **buf_write = &device->buf_write;
	size_t *buf_size = &device->buf_size;
	int old_buf_size = *buf_size;

	/* Get a report from the device */
	size = getline(buf_read, buf_size, file);
	if (size < 0) {
		perror("read");
		return size;
	}

	if (old_buf_size != *buf_size) {
		if (old_buf_size)
			*buf_write = realloc(*buf_write, *buf_size);
		else
			*buf_write = malloc(*buf_size);
		if (!*buf_write) {
			perror("memory allocation");
			return -1;
		}
	}

	if (size > 8 && strncmp(*buf_read, "report ", 7) == 0) {
		int rsize;
		char numbered[16];
		sscanf(*buf_read, "report (size %d) (%[^)]) = %[^\n]\n", &rsize, numbered, *buf_write);
		printf("E: ");
		print_currenttime(starttime);
		printf(" %d %s\n", rsize, *buf_write);
		fflush(stdout);
		return size;
	}

	return 0; /* not a raw report */
}

static int read_hidraw_event(struct hid_recorder_device *device)
{
	int fd = device->fd;
	struct timeval *starttime = &state.starttime;
	char buf[4096];
	int i, res;

	/* Get a report from the device */
	res = read(fd, buf, sizeof(buf));
	if (res < 0) {
		perror("read");
	} else {
		printf("E: ");
		print_currenttime(starttime);
		printf(" %d", res);

		for (i = 0; i < res; i++)
			printf(" %02hhx", buf[i]);
		printf("\n");
		fflush(stdout);
	}
	return res;
}

static void exit_recording_message()
{
	if (!state.event_count)
		fprintf(stderr, "\nNo events where recorded.\n"
				"You may need to %s the option \"--debugfs\" to get more recordings.\n",
			state.mode == MODE_HIDRAW ? "add" : "remove");
}

static int read_event(struct hid_recorder_device *device)
{
	if (state.current != device){
		printf("D: %d\n", device->idx);
		state.current = device;
	}

	if (device->hid_dbg_file)
		return read_hiddbg_event(device);

	return read_hidraw_event(device);
}

static int open_device(const char *filename, int idx, struct hid_recorder_device *device)
{
	int ret;
	char *hid_dbg_event = NULL;
	int fd = open(filename, O_RDWR);

	if (fd < 0)
		return EXIT_FAILURE;

	device->fd = fd;
	device->idx = idx;
	if (fetch_hidraw_information(device) != EXIT_SUCCESS) {
		ret = EXIT_FAILURE;
		goto out_err;
	}

	/* try to use hid debug sysfs instead of hidraw to retrieve the events */
	if (state.mode == MODE_HID_DEBUGFS)
		hid_dbg_event = find_hid_dbg(&device->info, &device->rpt_desc);

	if (hid_dbg_event) {
		fprintf(stderr, "reading debug interface %s instead of %s\n",
			hid_dbg_event, filename);
		/* keep fd opened to keep the device powered */
		device->hid_dbg_file = fopen(hid_dbg_event, "r");
		if (!device->hid_dbg_file) {
			perror("Unable to open HID debug interface");
			ret = EXIT_FAILURE;
			goto out_err;
		}
	}

	device->filename = strdup(filename);

	if (hid_dbg_event)
		free(hid_dbg_event);
	return 0;

out_err:
	if (hid_dbg_event)
		free(hid_dbg_event);
	if (device->hid_dbg_file)
		fclose(device->hid_dbg_file);
	if (fd > 0)
		close(fd);
	return ret;
}

static void destroy_device(struct hid_recorder_device *device)
{
	if (!device->fd)
		return;

	if (device->hid_dbg_file)
		fclose(device->hid_dbg_file);
	if (device->buf_size) {
		free(device->buf_read);
		free(device->buf_write);
	}
	free(device->filename);
	close(device->fd);
	device->fd = 0;
}

static void destroy_devices(struct hid_recorder_state *state)
{
	int i;

	for (i = 0; i < state->device_count; i++)
		destroy_device(&state->devices[i]);

	free(state->devices);
	free(state->fds);
}

static int cleanup_one_device(struct hid_recorder_state *state, int idx)
{
	/* index not in range, aborting */
	if (idx >= state->device_count || idx < 0)
		return state->device_count;

	/* remove the device */
	destroy_device(&state->devices[idx]);
	state->device_count--;

	/* the device was not at the end of the list, move the ones after */
	if (idx < state->device_count) {
		memmove(&state->devices[idx], &state->devices[idx + 1],
			(state->device_count - idx) * sizeof(struct hid_recorder_device));
		memmove(&state->fds[idx], &state->fds[idx + 1],
			(state->device_count - idx) * sizeof(struct pollfd));
	}

	/* clear the end of the array to prevent any double free */
	memset(&state->devices[state->device_count], 0, sizeof(struct hid_recorder_device));

	return state->device_count;
}

static void signal_callback_handler(int signum)
{
	exit_recording_message();

	destroy_devices(&state);

	/* Terminate program */
	exit(signum);
}

int main(int argc, char **argv)
{
	int ret, i;
	char *filename;
	int device_count;
	struct hid_recorder_device *devices, *device;
	struct pollfd *fds;

	state.mode = MODE_HIDRAW;

	while (1) {
		int option_index = 0;
		int c = getopt_long(argc, argv, "hd", long_options, &option_index);
		if (c == -1)
			break;
		switch (c) {
		case 'd':
			state.mode = MODE_HID_DEBUGFS;
			break;
		default:
			return usage();
		}
	}

	if (optind < argc) {
		device_count = argc - optind;
		filename = strdup(argv[optind++]);
	} else {
		if (getuid() != 0)
			fprintf(stderr, "Not running as root, some devices "
				"may not be available.\n");

		filename = scan_devices();
		if (!filename)
			return usage();
		device_count = 1;
	}

	if (device_count <= 0)
		return usage();

	devices = calloc(device_count, sizeof(struct hid_recorder_device));
	fds = calloc(device_count, sizeof(struct pollfd));
	if (!devices || !fds)
		return -ENOMEM;

	state.devices = devices;
	state.device_count = device_count;
	state.fds = fds;
	memset(&state.starttime, 0x0, sizeof(state.starttime));

	for (i = 0; i < device_count; i++) {
		device = &devices[i];
		ret = open_device(filename, i, device);
		if (ret) {
			perror("Unable to open device");
			free(filename);
			goto out_clean;
		}
		fds[i].fd = device->fd;
		fds[i].events = POLLIN;
		free(filename);
		if (device_count - i > 1)
			filename = strdup(argv[optind++]);
	}

	signal(SIGINT, signal_callback_handler);

	do {
		ret = poll(fds, device_count, -1);
		if (ret >= 0) {
			for (i = 0; i < device_count; i++) {
				if (fds[i].revents & POLLIN) {
					ret = read_event(&devices[i]);
					if (ret > 0)
						state.event_count++;
				} else if (fds[i].revents & POLLHUP) {
					device_count = cleanup_one_device(&state, i);
				}
			}
		}
	} while (ret >= 0 && device_count > 0);

out_clean:
	exit_recording_message();
	destroy_devices(&state);
	return ret;
}
