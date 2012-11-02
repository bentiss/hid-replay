noinst_PROGRAMS =

bin_PROGRAMS = \
	hid-replay \
	hid-recorder

INCLUDES=-I$(top_srcdir)/include/

# man page generation
if HAVE_DOCTOOLS
# actual man pages
man_pages_sources = hid-replay.txt hid-recorder.txt
# shadow man pages
man_pages_shadows =

man_pages = $(man_pages_sources:.txt=.1) $(man_pages_shadows)

SUFFIXES = .1 .txt .xml

.xml.1:
	@$(XMLTO) man $<

.txt.xml:
	@$(ASCIIDOC) -b docbook -d manpage -o $@ $<

dist_man_MANS = $(man_pages)
CLEANFILES = $(dist_man_MANS)
MAINTAINERCLEANFILES = $(man_pages) *.xml
endif
