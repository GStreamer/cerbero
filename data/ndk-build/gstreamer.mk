$(call assert-defined, GSTREAMER_SDK_ROOT GSTREAMER_PLUGINS)

# Setup variable variables
ifndef GSTREAMER_STATIC_PLUGINS_PATH
GSTREAMER_STATIC_PLUGINS_PATH := lib/gstreamer-0.10
endif
GSTREAMER_STATIC_PLUGINS_PATH := $(GSTREAMER_SDK_ROOT)/lib/gstreamer-0.10/static

ifndef GSTREAMER_NDK_BUILD_PATH
GSTREAMER_NDK_BUILD_PATH := $(GSTREAMER_SDK_ROOT)/share/gst-android/ndk-build
endif

G_IO_MODULES_PATH := $(GSTREAMER_SDK_ROOT)/lib/gio/modules

GSTREAMER_ANDROID_MODULE_NAME=gstreamer_android
GSTREAMER_ANDROID_LO=$(GSTREAMER_ANDROID_MODULE_NAME).lo
GSTREAMER_ANDROID_SO=lib$(GSTREAMER_ANDROID_MODULE_NAME).so
GSTREAMER_ANDROID_C=$(GSTREAMER_ANDROID_MODULE_NAME).c

# Make pkg-config and libtool relocatables
# * pkg-config:
# set PKG_CONFIG_LIBDIR and override the prefix and libdir variables
PKG_CONFIG_ORIG := PKG_CONFIG_LIBDIR=$(GSTREAMER_SDK_ROOT)/lib/pkgconfig pkg-config
PKG_CONFIG := $(PKG_CONFIG_ORIG) --define-variable=prefix=$(GSTREAMER_SDK_ROOT) --define-variable=libdir=$(GSTREAMER_SDK_ROOT)/lib
# * libtool:
# Use the nev variables LT_OLD_PREFIX and LT_NEW_PREFIX which replaces
# the build prefix with the installation one
BUILD_PREFIX := $(shell $(PKG_CONFIG_ORIG) --variable=prefix glib-2.0)
LIBTOOL := LT_OLD_PREFIX=$(BUILD_PREFIX) LT_NEW_PREFIX=$(GSTREAMER_SDK_ROOT) $(GSTREAMER_NDK_BUILD_PATH)/libtool


# Declare a prebuilt library module, a shared library including
# gstreamer, its dependencies and all its plugins.
# Since the shared library is not really prebuilt, but will be built
# using the defined rules in this file, we can't use the
# PREBUILT_SHARED_LIBRARY makefiles like explained in the docs,
# as it checks for the existance of the shared library. We therefore
# use a custom gstreamer_prebuilt.mk, which skips this step
LOCAL_PATH := $(call my-dir)
include $(CLEAR_VARS)
LOCAL_MODULE := $(GSTREAMER_ANDROID_MODULE_NAME)
LOCAL_SRC_FILES := $(GSTREAMER_ANDROID_SO)
LOCAL_BUILD_SCRIPT := PREBUILT_SHARED_LIBRARY
LOCAL_MODULE_CLASS := PREBUILT_SHARED_LIBRARY
LOCAL_MAKEFILE     := $(local-makefile)

LOCAL_PREBUILT_PREFIX := lib
LOCAL_PREBUILT_SUFFIX := .so
LOCAL_EXPORT_C_INCLUDES := $(shell  echo `$(PKG_CONFIG) gstreamer-0.10 --cflags-only-I` | sed 's/-I//g')
LOCAL_EXPORT_C_INCLUDES := $(LOCAL_EXPORT_C_INCLUDES) $(GSTREAMER_SDK_ROOT)/include

include $(GSTREAMER_NDK_BUILD_PATH)/gstreamer_prebuilt.mk
# This trigger the build of our library using our custom rules
$(GSTREAMER_ANDROID_SO): buildsharedlibrary copyjavasource


##################################################################
#   Our custom rules to create a shared libray with gstreamer    #
#   and the requested plugins in GSTREAMER_PLUGINS starts here   #
##################################################################

# Some plugins uses a different name for the module name, like the playback
# plugin, which uses playbin for the module name: libgstplaybin.so
fix-plugin-name = \
	$(shell echo $(GSTREAMER_PLUGINS_LIBS) | sed 's/gst$1/gst$2/g')

fix-deps = \
	$(shell echo $(GSTREAMER_ADNROID_LIBS) | sed 's/$1/$1 $2/g')

# Generate list of plugins links (eg: -lcoreelements -lvideoscale)
GSTREAMER_PLUGINS_LIBS=$(foreach plugin, $(GSTREAMER_PLUGINS), -lgst$(plugin))
GSTREAMER_PLUGINS_LIBS := $(call fix-plugin-name,playback,playbin)
GSTREAMER_PLUGINS_LIBS := $(call fix-plugin-name,uridecodebin,decodebin2)
GSTREAMER_PLUGINS_LIBS := $(call fix-plugin-name,encoding,encodebin)
GSTREAMER_PLUGINS_LIBS := $(call fix-plugin-name,soup,souphttpsrc)
GSTREAMER_PLUGINS_LIBS := $(shell echo $(GSTREAMER_PLUGINS_LIBS) | sed 's/gstgnonlin/gnl/g')
# Generate the plugins' declaration strings
GSTREAMER_PLUGINS_DECLARE=$(foreach plugin, $(GSTREAMER_PLUGINS), \
			GST_PLUGIN_STATIC_DECLARE($(plugin));\n)
# Generate the plugins' registration strings
GSTREAMER_PLUGINS_REGISTER=$(foreach plugin, $(GSTREAMER_PLUGINS), \
			GST_PLUGIN_STATIC_REGISTER($(plugin));\n)
# Generate list of gio modules
G_IO_MODULES_PATH := $(foreach path, $(G_IO_MODULES_PATH), -L$(path))
G_IO_MODULES_LIBS := $(foreach module, $(G_IO_MODULES), -lgio$(module))
G_IO_MODULES_DECLARE := $(foreach module, $(G_IO_MODULES), \
			G_IO_MODULE_DECLARE(gnutls);\n)
G_IO_MODULES_LOAD := $(foreach module, $(G_IO_MODULES), \
			G_IO_MODULE_LOAD(gnutls);\n)
# Get the full list of libraries
GSTREAMER_ADNROID_LIBS := $(GSTREAMER_PLUGINS_LIBS) $(G_IO_MODULES_LIBS) -llog -lz
# Fix deps for giognutls
GSTREAMER_ADNROID_LIBS :=  $(call fix-deps,-lgiognutls, -lhogweed)
GSTREAMER_ANDROID_CFLAGS := $(shell $(PKG_CONFIG) --cflags gstreamer-0.10) -I$(GSTREAMER_SDK_ROOT)/include


# Generates a source files that declares and register all the required plugins
genstatic:
	cp $(GSTREAMER_NDK_BUILD_PATH)/gstreamer_android.c.in $(GSTREAMER_ANDROID_MODULE_NAME).c
	@sed -i 's/@PLUGINS_DECLARATION@/$(GSTREAMER_PLUGINS_DECLARE)/g' $(GSTREAMER_ANDROID_MODULE_NAME).c
	@sed -i 's/@PLUGINS_REGISTRATION@/$(GSTREAMER_PLUGINS_REGISTER)/g' $(GSTREAMER_ANDROID_MODULE_NAME).c
	@sed -i 's/@G_IO_MODULES_LOAD@/$(G_IO_MODULES_LOAD)/g' $(GSTREAMER_ANDROID_MODULE_NAME).c
	@sed -i 's/@G_IO_MODULES_DECLARE@/$(G_IO_MODULES_DECLARE)/g' $(GSTREAMER_ANDROID_MODULE_NAME).c

$(GSTREAMER_ANDROID_LO): genstatic
	$(LIBTOOL) --tag=CC --mode=compile $(_CC) --sysroot=$(SYSROOT) $(CFLAGS) -c $(GSTREAMER_ANDROID_C) -Wall -Werror -o $(GSTREAMER_ANDROID_LO) $(GSTREAMER_ANDROID_CFLAGS)

# The goal is to create a shared library containing gstreamer
# its plugins and its dependencies.
# * First, we need to trick libtool, asking it to create an
# executable program so that it includes all the static libraries,
# but passing the -shared option directly to the
# linker with -XCClinker to end-up creating a shared library
#
# * -fuse-ld=gold is used to fix a bug in the default linker see:
# (https://groups.google.com/forum/?fromgroups=#!topic/android-ndk/HaLycHImqL8)
#
# * libz is not listed as dependency in libxml2.la and even adding it doesn't help
# libtool (although it should :/), so we explicitly link -lz at the very end.
buildsharedlibrary: $(GSTREAMER_ANDROID_LO)
	$(LIBTOOL) --tag=CC --mode=link $(_CC) $(LDFLAGS) --sysroot=$(SYSROOT) \
		-static-libtool-libs \
		-o $(GSTREAMER_ANDROID_SO)  $(GSTREAMER_ANDROID_LO) \
		-L$(GSTREAMER_STATIC_PLUGINS_PATH) $(G_IO_MODULES_PATH) \
		$(GSTREAMER_ADNROID_LIBS) \
		-XCClinker -shared -fuse-ld=gold

copyjavasource:
	@mkdir -p src/com/gst_sdk
	@cp $(GSTREAMER_NDK_BUILD_PATH)/GStreamer.java src/com/gst_sdk
