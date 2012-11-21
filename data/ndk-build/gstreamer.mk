# cerbero - a multi-platform build system for Open Source software
# Copyright (C) 2012 Andoni Morales Alastruey <ylatuya@gmail.com>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.
#
# You should have received a copy of the GNU Library General Public
# License along with this library; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.

$(call assert-defined, GSTREAMER_SDK_ROOT)
$(if $(wildcard $(GSTREAMER_SDK_ROOT)),,\
  $(error "The directory GSTREAMER_SDK_ROOT=$(GSTREAMER_SDK_ROOT) does not exists")\
)


#####################
#  Setup variables  #
#####################

ifndef GSTREAMER_PLUGINS
  $(info "The list of GSTREAMER_PLUGINS is empty")
endif

# Path for GStreamer static plugins
ifndef GSTREAMER_STATIC_PLUGINS_PATH
GSTREAMER_STATIC_PLUGINS_PATH := lib/gstreamer-0.10
endif
GSTREAMER_STATIC_PLUGINS_PATH := $(GSTREAMER_SDK_ROOT)/lib/gstreamer-0.10/static

# Path for the NDK integration makefiles
ifndef GSTREAMER_NDK_BUILD_PATH
GSTREAMER_NDK_BUILD_PATH := $(GSTREAMER_SDK_ROOT)/share/gst-android/ndk-build
endif

# Include tools
include $(GSTREAMER_NDK_BUILD_PATH)/tools.mk

# Path for the static GIO modules
G_IO_MODULES_PATH := $(GSTREAMER_SDK_ROOT)/lib/gio/modules/static

# Host tools
ifeq ($(HOST_OS),windows)
    HOST_SED := $(GSTREAMER_NDK_BUILD_PATH)/tools/windows/sed
    GSTREAMER_LD :=
else
endif

GSTREAMER_ANDROID_MODULE_NAME := gstreamer_android
GSTREAMER_BUILD_DIR           := gst-build
GSTREAMER_ANDROID_O           := $(GSTREAMER_BUILD_DIR)/$(GSTREAMER_ANDROID_MODULE_NAME).o
GSTREAMER_ANDROID_SO          := $(GSTREAMER_BUILD_DIR)/lib$(GSTREAMER_ANDROID_MODULE_NAME).so
GSTREAMER_ANDROID_C           := $(GSTREAMER_BUILD_DIR)/$(GSTREAMER_ANDROID_MODULE_NAME).c
GSTREAMER_ANDROID_C_IN        := $(GSTREAMER_NDK_BUILD_PATH)/gstreamer_android.c.in
GSTREAMER_DEPS                := $(GSTREAMER_EXTRA_DEPS) gstreamer-0.10
GSTREAMER_LD                  := -fuse-ld=gold

################################
#  NDK Build Prebuilt library  #
################################

# Declare a prebuilt library module, a shared library including
# gstreamer, its dependencies and all its plugins.
# Since the shared library is not really prebuilt, but will be built
# using the defined rules in this file, we can't use the
# PREBUILT_SHARED_LIBRARY makefiles like explained in the docs,
# as it checks for the existance of the shared library. We therefore
# use a custom gstreamer_prebuilt.mk, which skips this step

include $(CLEAR_VARS)
LOCAL_MODULE            := $(GSTREAMER_ANDROID_MODULE_NAME)
LOCAL_SRC_FILES         := $(GSTREAMER_ANDROID_SO)
LOCAL_BUILD_SCRIPT      := PREBUILT_SHARED_LIBRARY
LOCAL_MODULE_CLASS      := PREBUILT_SHARED_LIBRARY
LOCAL_MAKEFILE          := $(local-makefile)
LOCAL_PREBUILT_PREFIX   := lib
LOCAL_PREBUILT_SUFFIX   := .so
LOCAL_EXPORT_C_INCLUDES := $(subst -I$1, $1, $(call pkg-config-get-includes,$(GSTREAMER_DEPS)))
LOCAL_EXPORT_C_INCLUDES += $(GSTREAMER_SDK_ROOT)/include


##################################################################
#   Our custom rules to create a shared libray with gstreamer    #
#   and the requested plugins in GSTREAMER_PLUGINS starts here   #
##################################################################

include $(GSTREAMER_NDK_BUILD_PATH)/gstreamer_prebuilt.mk
# This triggers the build of our library using our custom rules
$(GSTREAMER_ANDROID_SO): buildsharedlibrary copyjavasource copyfontsres


# Some plugins use a different name for the module name, like the playback
# plugin, which uses playbin for the module name: libgstplaybin.so
fix-plugin-name = \
	$(subst gst$1 ,gst$2 ,$(GSTREAMER_PLUGINS_LIBS))

fix-deps = \
	$(subst $1,$1 $2,$(GSTREAMER_ANDROID_LIBS))


# Generate list of plugin links (eg: -lcoreelements -lvideoscale)
GSTREAMER_PLUGINS_LIBS       := $(foreach plugin, $(GSTREAMER_PLUGINS), -lgst$(plugin) )
GSTREAMER_PLUGINS_LIBS       := $(call fix-plugin-name,playback,playbin)
GSTREAMER_PLUGINS_LIBS       := $(call fix-plugin-name,uridecodebin,decodebin2)
GSTREAMER_PLUGINS_LIBS       := $(call fix-plugin-name,encoding,encodebin)
GSTREAMER_PLUGINS_LIBS       := $(call fix-plugin-name,soup,souphttpsrc)
GSTREAMER_PLUGINS_LIBS       := $(call fix-plugin-name,gstsiren,siren)
GSTREAMER_PLUGINS_LIBS       := $(call fix-plugin-name,sdp,sdpelem)
GSTREAMER_PLUGINS_LIBS       := $(call fix-plugin-name,gstrtpmanager,rtpmanager)
GSTREAMER_PLUGINS_LIBS       := $(call fix-plugin-name,scaletempo,scaletempoplugin)
GSTREAMER_PLUGINS_LIBS       := $(call fix-plugin-name,mpegdemux2,mpegdemux)
GSTREAMER_PLUGINS_LIBS       := $(call fix-plugin-name,realmedia,rmdemux)
GSTREAMER_PLUGINS_LIBS       := $(subst gstgnonlin,gnl,$(GSTREAMER_PLUGINS_LIBS))

# Generate the plugins' declaration strings
GSTREAMER_PLUGINS_DECLARE    := $(foreach plugin, $(GSTREAMER_PLUGINS), \
			GST_PLUGIN_STATIC_DECLARE($(plugin));\n)
# Generate the plugins' registration strings
GSTREAMER_PLUGINS_REGISTER   := $(foreach plugin, $(GSTREAMER_PLUGINS), \
			GST_PLUGIN_STATIC_REGISTER($(plugin));\n)

# Generate list of gio modules
G_IO_MODULES_PATH            := $(foreach path, $(G_IO_MODULES_PATH), -L$(path))
G_IO_MODULES_LIBS            := $(foreach module, $(G_IO_MODULES), -lgio$(module))
G_IO_MODULES_DECLARE         := $(foreach module, $(G_IO_MODULES), \
			G_IO_MODULE_DECLARE(gnutls);\n)
G_IO_MODULES_LOAD            := $(foreach module, $(G_IO_MODULES), \
			G_IO_MODULE_LOAD(gnutls);\n)

# Get the full list of libraries
# link at least to gstreamer-0.10 in case the plugins list is empty
GSTREAMER_ANDROID_LIBS       := $(call pkg-config-get-libs,$(GSTREAMER_DEPS))
GSTREAMER_ANDROID_LIBS       += $(GSTREAMER_PLUGINS_LIBS) $(G_IO_MODULES_LIBS) -llog -lz
GSTREAMER_ANDROID_WHOLE_AR   := $(call pkg-config-get-libs-no-deps,$(GSTREAMER_DEPS))
# Fix deps for giognutls
GSTREAMER_ANDROID_LIBS       := $(call fix-deps,-lgiognutls, -lhogweed)
GSTREAMER_ANDROID_CFLAGS     := $(call pkg-config-get-includes,$(GSTREAMER_DEPS)) -I$(GSTREAMER_SDK_ROOT)/include

# Create the link command
GSTREAMER_ANDROID_CMD        := $(call libtool-link,$(_CC) $(LDFLAGS) -shared --sysroot=$(SYSROOT) \
	-o $(GSTREAMER_ANDROID_SO) $(GSTREAMER_ANDROID_O) \
	-L$(GSTREAMER_SDK_ROOT)/lib -L$(GSTREAMER_STATIC_PLUGINS_PATH) $(G_IO_MODULES_PATH) \
	$(GSTREAMER_ANDROID_LIBS), $(GSTREAMER_LD)) -Wl,-no-undefined $(GSTREAMER_LD)
GSTREAMER_ANDROID_CMD        := $(call libtool-whole-archive,$(GSTREAMER_ANDROID_CMD),$(GSTREAMER_ANDROID_WHOLE_AR))


# Generates a source file that declares and registers all the required plugins
genstatic:
	@$(HOST_ECHO) "GStreamer      : [GEN] => $(GSTREAMER_ANDROID_C)"
	@$(call host-mkdir,$(GSTREAMER_BUILD_DIR))
	@$(call host-cp,$(GSTREAMER_ANDROID_C_IN),$(GSTREAMER_ANDROID_C))
	@$(HOST_SED) -i "s/@PLUGINS_DECLARATION@/$(GSTREAMER_PLUGINS_DECLARE)/g" $(GSTREAMER_ANDROID_C)
	@$(HOST_SED) -i "s/@PLUGINS_REGISTRATION@/$(GSTREAMER_PLUGINS_REGISTER)/g" $(GSTREAMER_ANDROID_C)
	@$(HOST_SED) -i "s/@G_IO_MODULES_LOAD@/$(G_IO_MODULES_LOAD)/g" $(GSTREAMER_ANDROID_C)
	@$(HOST_SED) -i "s/@G_IO_MODULES_DECLARE@/$(G_IO_MODULES_DECLARE)/g" $(GSTREAMER_ANDROID_C)

# Compile the source file
$(GSTREAMER_ANDROID_O): genstatic
	@$(HOST_ECHO) "GStreamer      : [COMPILE] => $(GSTREAMER_ANDROID_C)"
	@$(_CC) --sysroot=$(SYSROOT) $(CFLAGS) -c $(GSTREAMER_ANDROID_C) -Wall -Werror -o $(GSTREAMER_ANDROID_O) $(GSTREAMER_ANDROID_CFLAGS)

# Creates a shared library including gstreamer, its plugins and all the dependencies
buildsharedlibrary: $(GSTREAMER_ANDROID_O)
	@$(HOST_ECHO) "GStreamer      : [LINK] => $(GSTREAMER_ANDROID_SO)"
	@$(_CC) $(GSTREAMER_ANDROID_CMD)

copyjavasource:
	@$(call host-mkdir,src/com/gstreamer)
	@$(call host-cp,$(GSTREAMER_NDK_BUILD_PATH)/GStreamer.java,src/com/gstreamer)

copyfontsres:
	@$(call host-mkdir,assets/fontconfig)
	@$(call host-mkdir,assets/fontconfig/fonts/truetype/)
	@$(call host-cp,$(GSTREAMER_NDK_BUILD_PATH)/fontconfig/fonts.conf,assets/fontconfig)
	@$(call host-cp,$(GSTREAMER_NDK_BUILD_PATH)/fontconfig/fonts/Ubuntu-R.ttf,assets/fontconfig/fonts/truetype)
