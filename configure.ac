# Initialize Autoconf
AC_PREREQ([2.60])
AC_INIT([HID device replay],
        [0.7.0],
        [],
        [hid-replay])
AC_CONFIG_SRCDIR([Makefile.am])
AC_CONFIG_HEADERS([config.h])
AC_CONFIG_AUX_DIR([config-aux])

# Initialize Automake
AM_INIT_AUTOMAKE([foreign dist-bzip2])
AM_MAINTAINER_MODE

LIB_VERSION=1:0:0
AC_SUBST([LIB_VERSION])

# Checks for programs.
AC_PROG_CC
AC_PROG_INSTALL

AC_CHECK_HEADERS([linux/uhid.h],
	AM_CONDITIONAL(HAVE_UHID, true),
	[AM_CONDITIONAL(HAVE_UHID, false)
	 AC_MSG_WARN([uhid.h not found - cannot create hid-replay])])


# man page generation
AC_ARG_VAR([XMLTO], [Path to xmlto command])
AC_PATH_PROG([XMLTO], [xmlto])
AC_ARG_VAR([ASCIIDOC], [Path to asciidoc command])
AC_PATH_PROG([ASCIIDOC], [asciidoc])
AM_CONDITIONAL([HAVE_DOCTOOLS], [test "x$XMLTO" != "x" && test "x$ASCIIDOC" != "x"])
if test "x$XMLTO" = "x" || test "x$ASCIIDOC" = "x"; then
	AC_MSG_WARN([xmlto or asciidoc not found - cannot create man pages without it])
fi


AC_CONFIG_FILES([Makefile
                 src/Makefile])
AC_OUTPUT
