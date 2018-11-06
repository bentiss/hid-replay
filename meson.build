project('hid-replay', 'c', 
	version: '0.7.1',
	license: 'GPL2+',
	default_options: ['c_std=gnu99', 'warning_level=2'],
	meson_version: '>= 0.47.0')

dir_man1 = join_paths(get_option('prefix'), get_option('mandir'), '1')

includes_include = include_directories('include')

cc = meson.get_compiler('c')
cflags = ['-Wno-unused-parameter', '-DHAVE_CONFIG_H']
add_project_arguments(cflags, language : 'c')

# We need a config.h for the ccan headers
config_h = configuration_data()
config_h.set('_GNU_SOURCE', '1')
configure_file(output: 'config.h',
	       install: false,
	       configuration: config_h)

executable('hid-recorder',
	   'src/hid-recorder.c',
	   install: true,
	   include_directories: [includes_include])

if not cc.check_header('linux/uhid.h')
	warning('linux/uhid.h not found - cannot create hid-replay')
else
	executable('hid-replay',
		   'src/hid-replay.c',
		   install: true,
		   include_directories: [includes_include])
endif

xmlto = find_program('xmlto', required: false)
asciidoc = find_program('asciidoc', required: false)
if xmlto.found() and asciidoc.found()
	manpages = ['hid-replay.txt', 'hid-recorder.txt']
	foreach f: manpages 
		f_xml = custom_target('xml for @0@'.format(f),
				      input: join_paths('src', f),
				      output: '@BASENAME@.xml',
				      command: [asciidoc.path(), '-b', 'docbook', '-d', 'manpage', '-o', '@BASENAME@.xml', '@INPUT@'],
				      install: false)
		custom_target('man page for @0@'.format(f),
			      input: f_xml,
			      output: '@BASENAME@.1',
			      command: [xmlto.path(), 'man', f_xml],
			      install: true,
			      install_dir: dir_man1)
	endforeach
else
	warning('xmlto or asciidoc not found - cannot create man pages without it')
endif
