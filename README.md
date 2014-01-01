Rhythmsub
=========

Subsonic support has finally come to Rhythmbox.

Installation
------------

Clone this repository into your Rhythmbox plugins directory:

    $ mkdir -p ~/.local/share/rhythmbox/plugins
    $ git clone https://github.com/LukeCarrier/rhythmbox-rhythmsub.git \
                ~/.local/share/rhythmbox/plugins/rhythmsub

Then copy the gsettings schema into the global schema directory:

    $ cp ~/.local/share/rhythmbox/plugins/rhythmsub/*.gschema.xml \
         /usr/share/glib-2.0/schemas
    $ sudo glib-compile-schemas /usr/share/glib-2.0/schemas

Testing (without installation)
------------------------------

It's possible to run Rhythmsub without installing the gsettings schema globally.
First, copy the schema file out of the plugin directory into your own local
schema directory:

    $ mkdir -p ~/.local/share/glib-2.0/schemas
    $ ln -s ~/.local/share/rhythmbox/plugins/rhythmsub/*.gschema.xml \
         ~/.local/share/glib-2.0/schemas
    $ glib-compile-schemas ~/.local/share/glib-2.0/schemas

Then, when launching Rhythmbox, do so from the terminal with a command like the
following:

    $ GSETTINGS_SCHEMA_DIR=$HOME/.local/share/glib-2.0/schemas rhythmbox -d

Known issues
------------

* The version of gvfsd-http presently shipping in Ubuntu leaks file descriptors
  and will crash frequently during library imports. This issue appears to have
  been fixed upstream by the Gnome developers; I'm trying to package it for
  Ubuntu.
