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
 * the Free Software Foundation, either version 3 of the License, or
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

/**
 * Print usage information.
 */
static int usage(void)
{
	printf("USAGE:\n");
	printf("   %s [/dev/hidrawX]\n", program_invocation_short_name);

	return EXIT_FAILURE;
}

static const struct option long_options[] = {
	{ "help", no_argument, NULL, 'h' },
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

int main(int argc, char **argv)
{
	int fd;
	int i, res, desc_size = 0;
	char buf[4096];
	struct hidraw_report_descriptor rpt_desc;
	struct hidraw_devinfo info;
	char *device;
	struct timeval starttime, currenttime;

	while (1) {
		int option_index = 0;
		int c = getopt_long(argc, argv, "h", long_options, &option_index);
		if (c == -1)
			break;
		return usage();
	}

	if (optind < argc)
		device = argv[optind++];
	else {
		if (getuid() != 0)
			fprintf(stderr, "Not running as root, some devices "
				"may not be available.\n");

		device = scan_devices();
		if (!device)
			return usage();
	}

	fd = open(device, O_RDWR);

	if (fd < 0) {
		perror("Unable to open device");
		return EXIT_FAILURE;
	}

	memset(&rpt_desc, 0x0, sizeof(rpt_desc));
	memset(&info, 0x0, sizeof(info));
	memset(buf, 0x0, sizeof(buf));
	memset(&starttime, 0x0, sizeof(starttime));

	/* Get Report Descriptor Size */
	res = ioctl(fd, HIDIOCGRDESCSIZE, &desc_size);
	if (res < 0)
		perror("HIDIOCGRDESCSIZE");

	/* Get Report Descriptor */
	rpt_desc.size = desc_size;
	res = ioctl(fd, HIDIOCGRDESC, &rpt_desc);
	if (res < 0) {
		perror("HIDIOCGRDESC");
	} else {
		printf("R: %d", desc_size);
		for (i = 0; i < rpt_desc.size; i++)
			printf(" %02hhx", rpt_desc.value[i]);
		printf("\n");
	}

	/* Get Raw Name */
	res = ioctl(fd, HIDIOCGRAWNAME(256), buf);
	if (res < 0)
		perror("HIDIOCGRAWNAME");
	else
		printf("N: %s\n", buf);

	/* Get Physical Location */
	res = ioctl(fd, HIDIOCGRAWPHYS(256), buf);
	if (res < 0)
		perror("HIDIOCGRAWPHYS");
	else
		printf("P: %s\n", buf);

	/* Get Raw Info */
	res = ioctl(fd, HIDIOCGRAWINFO, &info);
	if (res < 0) {
		perror("HIDIOCGRAWINFO");
	} else {
		printf("I: %x %04hx %04hx\n", info.bustype, info.vendor, info.product);
	}

	while (1) {
		/* Get a report from the device */
		res = read(fd, buf, sizeof(buf));
		if (res < 0) {
			perror("read");
			break;
		} else {
			if (!starttime.tv_sec && !starttime.tv_usec)
				gettimeofday(&starttime, NULL);
			gettimeofday(&currenttime, NULL);
			timeval_subtract(&currenttime, &currenttime, &starttime);
			printf("E: %lu.%06u %d", currenttime.tv_sec, (unsigned)currenttime.tv_usec, res);
			for (i = 0; i < res; i++)
				printf(" %02hhx", buf[i]);
			printf("\n");
			fflush(stdout);
		}
	}
	close(fd);
	return 0;
}
