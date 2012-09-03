$(call assert-defined, GSTREAMER_PLUGINS GSTREAMER_MK_PATH)

# Setup variable variables
ifndef GSTREAMER_STATIC_PLUGINS_PATH
GSTREAMER_STATIC_PLUGINS_PATH=/usr/lib/gstreamer-0.10
endif

ifndef GSTREAMER_ANDROID_LIBNAME
GSTREAMER_ANDROID_LIBNAME=gstreamer_android
endif
GSTREAMER_ANDROID_LO=$(GSTREAMER_ANDROID_LIBNAME).lo
GSTREAMER_ANDROID_SO=lib$(GSTREAMER_ANDROID_LIBNAME).so
GSTREAMER_ANDROID_C=$(GSTREAMER_ANDROID_LIBNAME).c


# Declare a prebuilt library module, a shared library including
# gstreamer, its dependencies and all its plugins.
# Since the shared library is not really prebuilt, but will be built
# using the defined rules in this file, we can't use the
# PREBUILT_SHARED_LIBRARY makefiles like explained in the docs,
# as it checks for the existance of the shared library. We therefore
# use a custom gstreamer_prebuilt.mk, which skips this step
LOCAL_PATH := $(call my-dir)
include $(CLEAR_VARS)
LOCAL_MODULE := $(GSTREAMER_ANDROID_LIBNAME)
LOCAL_SRC_FILES := $(GSTREAMER_ANDROID_SO)
LOCAL_BUILD_SCRIPT := PREBUILT_SHARED_LIBRARY
LOCAL_MODULE_CLASS := PREBUILT_SHARED_LIBRARY
LOCAL_MAKEFILE     := $(local-makefile)

LOCAL_PREBUILT_PREFIX := lib
LOCAL_PREBUILT_SUFFIX := .so
LOCAL_EXPORT_C_INCLUDES := $(shell  echo `pkg-config gstreamer-0.10 --cflags-only-I` | sed 's/-I//g')

include $(GSTREAMER_MK_PATH)/gstreamer_prebuilt.mk
# This trigger the build of our library using our custom rules
$(GSTREAMER_ANDROID_SO): buildsharedlibrary


##################################################################
#   Our custom rules to create a shared libray with gstreamer    #
#   and the requested plugins in GSTREAMER_PLUGINS starts here   #
##################################################################

# Generate list of plugins links (eg: -lcoreelements -lvideoscale)
GSTREAMER_PLUGINS_LIBS=$(foreach plugin, $(GSTREAMER_PLUGINS), -lgst$(plugin))
# Generate the plugins' declaration strings
GSTREAMER_PLUGINS_DECLARE=$(foreach plugin, $(GSTREAMER_PLUGINS), \
			GST_PLUGIN_STATIC_DECLARE($(plugin));\n)
# Generate the plugins' registration strings
GSTREAMER_PLUGINS_REGISTER=$(foreach plugin, $(GSTREAMER_PLUGINS), \
			GST_PLUGIN_STATIC_REGISTER($(plugin));\n)


# Generates a source files that declares and register all the required plugins
genstatic:
	echo "#include <gst/gst.h>\n" > $(GSTREAMER_ANDROID_LIBNAME).c
	echo "/* Declaration of static plugins */" >> $(GSTREAMER_ANDROID_LIBNAME).c
	echo " $(GSTREAMER_PLUGINS_DECLARE)" >> $(GSTREAMER_ANDROID_LIBNAME).c
	echo "/* Call this function to register static plugins */" >> $(GSTREAMER_ANDROID_LIBNAME).c
	echo "void gst_android_register_static_plugins(void) {\n" >> $(GSTREAMER_ANDROID_LIBNAME).c
	echo "$(GSTREAMER_PLUGINS_REGISTER)" >> $(GSTREAMER_ANDROID_LIBNAME).c
	echo "}" >> $(GSTREAMER_ANDROID_LIBNAME).c

$(GSTREAMER_ANDROID_LO): genstatic
	libtool --tag=CC --mode=compile  $(CC) $(CFLAGS) -c $(GSTREAMER_ANDROID_C)  -o $(GSTREAMER_ANDROID_LO) `pkg-config --cflags gstreamer-0.10`

# The goal is to create a shared library containing gstreamer
# its plugins and its dependencies. We need to trick libtool,
# asking it to create an executable program so that it includes all the
# static libraries, but passing the -shared option directly to the
# linker with -XCClinker to end-up creating a shared library
buildsharedlibrary: $(GSTREAMER_ANDROID_LO)
	libtool --tag=CC --mode=link $(CC) $(CFLAGS) \
		-static-libtool-libs \
		-o $(GSTREAMER_ANDROID_SO)  $(GSTREAMER_ANDROID_LO) \
		-L$(GSTREAMER_STATIC_PLUGINS_PATH) $(GSTREAMER_PLUGINS_LIBS) \
		-XCClinker -shared
