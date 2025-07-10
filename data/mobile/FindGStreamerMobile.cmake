# SPDX-FileCopyrightText: 2024 L. E. Segovia <amy@centricular.com>
# SPDX-License-Ref: LGPL-2.1-or-later

#[=======================================================================[.rst:
FindGStreamerMobile
-------

Creates additional mobile targets to install fonts and the CA certificate
bundle. Android and iOS only.

Imported Targets
^^^^^^^^^^^^^^^^

This module defines the following :prop_tgt:`INTERFACE` targets:

``GStreamer::fonts``
  A target that will install GStreamer's default fonts into the app.

``GStreamer::ca_certificates``
  A target that will install the NSS CA certificate bundle into the app.

This module defines the following :prop_tgt:`SHARED` targets:

``GStreamer::mobile``
  A target that will build the shared library consisting of GStreamer plus all the selected plugin components. (Android/iOS only)

Result Variables
^^^^^^^^^^^^^^^^

This will define the following variables:

``GStreamer_Mobile_FOUND``
  ON if the system has the GStreamer library.

Cache Variables
^^^^^^^^^^^^^^^

The following cache variables may also be set:

``GStreamer_CA_BUNDLE``
  Path to /etc/ssl/certs/ca-certificates.crt.
``GStreamer_UBUNTU_R_TTF``
  Path to the TrueType font Ubuntu R.
``GStreamer_FONTS_CONF``
  Path to /etc/fonts.conf.
``GStreamer_Mobile_MAKEDEF_PY``
  Path to the symbol visibility script generator.

Configuration Variables
^^^^^^^^^^^^^^^

Like with the main GStreamer library, setting the following variables is
required, depending on the operating system:

``GStreamer_ROOT_DIR``
  Installation prefix of the GStreamer SDK.

``GStreamer_JAVA_SRC_DIR``
  Target directory for deploying the selected plugins' Java classfiles to. (Android only)

``GStreamer_Mobile_MODULE_NAME``
  Name for the GStreamer::mobile shared library. Default is ``gstreamer_android`` (Android) or ``gstreamer_mobile`` (Darwin).

``GStreamer_Mobile_MODULE_FILE``
  If set, this file will be used as the source file for initializing all plugins statically.

``GStreamer_Mobile_MODULE_DEF``
  If set, this file will be used as the module definition file (Windows), version script (Linux) or exported symbols list (Darwin platforms) that will control the exported symbols.

``GStreamer_Mobile_SYMBOLS``
  Symbol pattern or patterns to filter which symbols will get exported. By default only symbols beginning with ``gst_``, ``GST_`` and ``_gst`` (and ``g_`` on Android) will be exported.

``GStreamer_ASSETS_DIR``
  Target directory for deploying assets to.

``G_IO_MODULES``
  Set this to the GIO modules you need, additional to any GStreamer plugins. (Usually set to ``gnutls`` or ``openssl``)

``G_IO_MODULES_PATH``
  Path for the static GIO modules.

#]=======================================================================]

if (GStreamer_Mobile_FOUND)
    return()
endif()

#####################
#  Setup variables  #
#####################

include(CheckIPOSupported)

if (NOT DEFINED GStreamer_ROOT_DIR AND DEFINED GSTREAMER_ROOT)
    set(GStreamer_ROOT_DIR ${GSTREAMER_ROOT})
endif()

set(_gst_required_vars)

if (ca_certificates IN_LIST GStreamerMobile_FIND_COMPONENTS)
    # for setting the default GTlsDatabase
    list(APPEND GStreamer_EXTRA_DEPS gio-2.0)
endif()

if (NOT DEFINED GStreamer_Mobile_SYMBOLS)
    set(GStreamer_Mobile_SYMBOLS)
endif()

if (ANDROID)
    list(APPEND GStreamer_EXTRA_DEPS zlib)
    if (NOT g_ IN_LIST GStreamer_Mobile_SYMBOLS)
        list(APPEND GStreamer_EXTRA_DEPS glib-2.0)
        # Extend with Glib and gst-android-1.0
        list(APPEND GStreamer_Mobile_SYMBOLS "g_" "JNI_On")
    endif()
endif()

if (ANDROID OR APPLE OR WIN32)
    set(GSTREAMER_IS_MOBILE ON)
else()
    set(GSTREAMER_IS_MOBILE OFF)
endif()

# Block shared GStreamer on mobile
if (GSTREAMER_IS_MOBILE)
    if (DEFINED GStreamer_USE_STATIC_LIBS)
        if (NOT GStreamer_USE_STATIC_LIBS)
            message(FATAL_ERROR "Shared library GStreamer is not supported on mobile or Windows platforms")
        endif()
    else()
        set(GStreamer_USE_STATIC_LIBS ON)
    endif()
endif()

# Now, let's set up targets for each of the components supplied
# These are the required plugins
set(_gst_plugins ${GStreamerMobile_FIND_COMPONENTS})
# These are custom handled targets, and must be skipped from the loop
list(REMOVE_ITEM _gst_plugins fonts ca_certificates mobile)
list(REMOVE_DUPLICATES _gst_plugins)

if (GStreamerMobile_FIND_REQUIRED)
find_package(GStreamer COMPONENTS ${_gst_plugins} REQUIRED)
else()
find_package(GStreamer COMPONENTS ${_gst_plugins})
endif()

# Infer now GStreamer_ROOT_DIR from the .pc file
# (and warn about it so that I know where the bug comes from)
if (NOT GStreamer_ROOT_DIR)
    pkg_get_variable(GStreamer_ROOT_DIR gstreamer-1.0 prefix)
    message(DEBUG "Inferring GStreamer_ROOT_DIR from the GStreamer installation location: ${GStreamer_ROOT_DIR}\nPlease file a bug if issues arise!")
endif()

# Prepare Android hotfixes for x264
if(ANDROID_ABI MATCHES "^armeabi")
    set(NEEDS_TEXTREL_ERROR TRUE)
    set(NEEDS_BSYMBOLIC_FIX TRUE)
elseif(ANDROID_ABI STREQUAL "x86")
    set(NEEDS_TEXTREL_ERROR TRUE)
    set(NEEDS_BSYMBOLIC_FIX TRUE)
# arm64: https://ffmpeg.org/pipermail/ffmpeg-devel/2022-July/298734.html 
elseif(ANDROID_ABI STREQUAL "x86_64" OR ANDROID_ABI STREQUAL "arm64-v8a")
    set(NEEDS_BSYMBOLIC_FIX TRUE)
endif()

# Set up output variables for Android
if(ANDROID)
    if (NOT DEFINED GStreamer_JAVA_SRC_DIR AND DEFINED GSTREAMER_JAVA_SRC_DIR)
        set(GStreamer_JAVA_SRC_DIR ${GSTREAMER_JAVA_SRC_DIR})
    elseif(NOT DEFINED GStreamer_JAVA_SRC_DIR)
        set(GStreamer_JAVA_SRC_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../src/")
    else()
        # Gradle does not let us access the root of the subproject
        # so we implement the ndk-build assumption ourselves
        set(GStreamer_JAVA_SRC_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../${GStreamer_JAVA_SRC_DIR}")
    endif()

    if(NOT DEFINED GStreamer_NDK_BUILD_PATH AND DEFINED GSTREAMER_NDK_BUILD_PATH)
        set(GStreamer_NDK_BUILD_PATH "${GSTREAMER_NDK_BUILD_PATH}")
    elseif(NOT DEFINED GStreamer_NDK_BUILD_PATH)
        set(GStreamer_NDK_BUILD_PATH  "${GStreamer_ROOT_DIR}/share/gst-android/ndk-build/")
    endif()
endif()

if(NOT DEFINED GStreamer_Mobile_MODULE_NAME)
    if (DEFINED GSTREAMER_ANDROID_MODULE_NAME)
        set(GStreamer_Mobile_MODULE_NAME "${GSTREAMER_ANDROID_MODULE_NAME}")
    elseif(ANDROID)
        set(GStreamer_Mobile_MODULE_NAME gstreamer_android)
    else()
        set(GStreamer_Mobile_MODULE_NAME gstreamer_mobile)
    endif()
endif()

if(ANDROID)
    if(NOT DEFINED GStreamer_ASSETS_DIR AND DEFINED GSTREAMER_ASSETS_DIR)
        set(GStreamer_ASSETS_DIR "${GSTREAMER_ASSETS_DIR}")
    elseif(NOT DEFINED GStreamer_ASSETS_DIR)
        set(GStreamer_ASSETS_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../src/assets/")
    else()
        # Same as above
        set(GStreamer_ASSETS_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../${GStreamer_ASSETS_DIR}")
    endif()

    if(NOT DEFINED GStreamer_NDK_BUILD_PATH AND DEFINED GSTREAMER_NDK_BUILD_PATH)
        set(GStreamer_NDK_BUILD_PATH "${GSTREAMER_NDK_BUILD_PATH}")
    elseif(NOT DEFINED GStreamer_NDK_BUILD_PATH)
        set(GStreamer_NDK_BUILD_PATH  "${GStreamer_ROOT_DIR}/share/gst-android/ndk-build/")
    endif()
elseif(IOS)
    if(NOT DEFINED GStreamer_ASSETS_DIR AND DEFINED GStreamer_ASSETS_DIR)
        set(GStreamer_ASSETS_DIR ${GStreamer_ASSETS_DIR})
    elseif(NOT DEFINED GStreamer_ASSETS_DIR)
        set(GStreamer_ASSETS_DIR "${CMAKE_CURRENT_SOURCE_DIR}/assets")
    else()
        # Same as above
        set(GStreamer_ASSETS_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../${GStreamer_ASSETS_DIR}")
    endif()
endif()

if (ANDROID)
    if (CMAKE_HOST_WIN32)
        set(PKG_CONFIG_EXECUTABLE "${GStreamer_NDK_BUILD_PATH}/tools/windows/pkg-config.exe")
    elseif (CMAKE_HOST_APPLE)
        set(PKG_CONFIG_EXECUTABLE "${GStreamer_NDK_BUILD_PATH}/tools/macos/pkg-config")
    endif()
endif()

if (ANDROID)
    file(READ "${GStreamer_NDK_BUILD_PATH}/GStreamer.java" JAVA_INPUT)
endif()

# If not previously filtered, set these up here
if (NOT DEFINED GSTREAMER_PLUGINS)
    # These are the required plugins
    set(GSTREAMER_PLUGINS ${_gst_plugins})
    # These are the API packages
    set(GSTREAMER_APIS ${GSTREAMER_PLUGINS})
    list(FILTER GSTREAMER_APIS INCLUDE REGEX "^api_")
    # Filter them out, although they're handled the same
    # they cannot be considered for the purposes of initialization
    list(FILTER GSTREAMER_PLUGINS EXCLUDE REGEX "^api_")
endif()

if (NOT TARGET GStreamer::mobile AND NOT DEFINED GStreamer_Mobile_MODULE_FILE)
    # Generate the plugins' declaration strings
    # (don't append a semicolon, CMake does it as part of the list)
    list(TRANSFORM GSTREAMER_PLUGINS
        PREPEND "\nGST_PLUGIN_STATIC_DECLARE\("
        OUTPUT_VARIABLE PLUGINS_DECLARATION
    )
    list(TRANSFORM PLUGINS_DECLARATION
        APPEND "\)"
        OUTPUT_VARIABLE PLUGINS_DECLARATION
    )
    if(PLUGINS_DECLARATION)
        set(PLUGINS_DECLARATION "${PLUGINS_DECLARATION};")
    endif()

    # Generate the plugins' registration strings
    list(TRANSFORM GSTREAMER_PLUGINS
        PREPEND "\nGST_PLUGIN_STATIC_REGISTER\("
        OUTPUT_VARIABLE PLUGINS_REGISTRATION
    )
    list(TRANSFORM PLUGINS_REGISTRATION
        APPEND "\)"
        OUTPUT_VARIABLE PLUGINS_REGISTRATION
    )
    if(PLUGINS_REGISTRATION)
        set(PLUGINS_REGISTRATION "${PLUGINS_REGISTRATION};")
    endif()

    # Generate list of gio modules
    if (NOT G_IO_MODULES)
        set(G_IO_MODULES)
    endif()
    list(TRANSFORM G_IO_MODULES
        PREPEND "gio"
        OUTPUT_VARIABLE G_IO_MODULES_LIBS
    )
    list(TRANSFORM G_IO_MODULES
        PREPEND "\nGST_G_IO_MODULE_DECLARE\("
        OUTPUT_VARIABLE G_IO_MODULES_DECLARE
    )
    list(TRANSFORM G_IO_MODULES_DECLARE
        APPEND "\);"
        OUTPUT_VARIABLE G_IO_MODULES_DECLARE
    )
    if(G_IO_MODULES_DECLARE)
        set(G_IO_MODULES_DECLARE "${G_IO_MODULES_DECLARE};")
    endif()
    list(TRANSFORM G_IO_MODULES
        PREPEND "\nGST_G_IO_MODULE_LOAD\("
        OUTPUT_VARIABLE G_IO_MODULES_LOAD
    )
    list(TRANSFORM G_IO_MODULES_LOAD
        APPEND "\)"
        OUTPUT_VARIABLE G_IO_MODULES_LOAD
    )
    if(G_IO_MODULES_LOAD)
        set(G_IO_MODULES_LOAD "${G_IO_MODULES_LOAD};")
    endif()

    # Generates a source file that declares and registers all the required plugins
    if (APPLE)
        configure_file(
            "${CMAKE_CURRENT_LIST_DIR}/GStreamer/gst_ios_init.m.in"
            "${GStreamer_Mobile_MODULE_NAME}.m"
        )
    else()
        configure_file(
            "${CMAKE_CURRENT_LIST_DIR}/GStreamer/gstreamer_android-1.0.c.in"
            "${GStreamer_Mobile_MODULE_NAME}.c"
        )
    endif()
endif()

if (NOT TARGET GStreamer::mobile)
    # Creates a shared library including gstreamer, its plugins and all the dependencies
    if (DEFINED GStreamer_Mobile_MODULE_FILE)
        if (WIN32)
            add_library(GStreamerMobile
                SHARED
                    "${GStreamer_Mobile_MODULE_FILE}"
            )
        else()
            add_library(GStreamerMobile
                SHARED
                    "${GStreamer_Mobile_MODULE_FILE}"
            )
        endif()
        set_target_properties(
            GStreamerMobile
            PROPERTIES
                C_VISIBILITY_PRESET hidden
                CXX_VISIBILITY_PRESET hidden
        )
    elseif (APPLE)
        add_library(GStreamerMobile SHARED)
        enable_language(OBJC OBJCXX)
        target_sources(GStreamerMobile
            PRIVATE
                "${GStreamer_Mobile_MODULE_NAME}.m"
        )
        set_source_files_properties("${GStreamer_Mobile_MODULE_NAME}.m"
            PROPERTIES
                LANGUAGE OBJC
        )
        find_library(Foundation_LIB Foundation REQUIRED)
        target_link_libraries(GStreamerMobile
            PRIVATE
                ${Foundation_LIB}
        )
    else ()
        add_library(GStreamerMobile
            SHARED
                "${GStreamer_Mobile_MODULE_NAME}.c"
        )
    endif()
    add_library(GStreamer::mobile ALIAS GStreamerMobile)

    # Assume it's C++ for the sake of gstsoundtouch
    set_target_properties(
        GStreamerMobile
        PROPERTIES
            OUTPUT_NAME ${GStreamer_Mobile_MODULE_NAME}
    )
    if (APPLE)
        set_target_properties(
            GStreamerMobile
            PROPERTIES
                LINKER_LANGUAGE OBJCXX
        )
    else()
        set_target_properties(
            GStreamerMobile
            PROPERTIES
                LINKER_LANGUAGE CXX
        )
    endif()
endif()

if (TARGET GStreamerMobile)
    string(REGEX MATCH "^([0-9]+)" _gst_version_major "${GStreamer_VERSION}")
    set_target_properties(
        GStreamerMobile
        PROPERTIES
            VERSION ${GStreamer_VERSION}
            SOVERSION ${_gst_version_major}
    )

    # Handle all libraries, even those specified with -l:libfoo.a (srt)
    # Due to the unavailability of pkgconf's `--maximum-traverse-depth`
    # on stock pkg-config, I attempt to simulate it through the shared
    # libraries listing.
    # If pkgconf is available, replace all PC_GStreamer_ entries with
    # PC_GStreamer_NoDeps and uncomment the code block above.
    if (ANDROID OR WIN32)
        # Prevent visibility inconsistencies between glib and others wrt.
        # libintl
        list(REMOVE_DUPLICATES PC_GStreamer_LIBRARIES)
    endif()
    set(_gst_libraries)
    foreach(LOCAL_LIB IN LISTS PC_GStreamer_LIBRARIES)
        string(MAKE_C_IDENTIFIER "_gst_${LOCAL_LIB}" GST_LOCAL_LIB)
        if (EXISTS "${${GST_LOCAL_LIB}}")
            list(APPEND _gst_libraries "${${GST_LOCAL_LIB}}")
        endif()
        # ELF doesn't export unless the function is actually used
        # or the .o is flattened into the inputs for the .so
        if (ANDROID)
            if ("${${GST_LOCAL_LIB}}" IN_LIST _gst_IGNORED_SYSTEM_LIBRARIES)
                target_link_libraries(GStreamerMobile PRIVATE
                    "${${GST_LOCAL_LIB}}"
                )
            else()
                target_link_libraries(GStreamerMobile PRIVATE
                    "-Wl,--whole-archive,${${GST_LOCAL_LIB}},--no-whole-archive"
                )
            endif()
        endif()
    endforeach()
    target_link_libraries(
        GStreamerMobile
        PRIVATE
            GStreamer::GStreamer
    )

    target_link_libraries(
        GStreamerMobile
        PRIVATE
            GStreamer::deps
    )

    target_link_options(
        GStreamerMobile
        PRIVATE
            $<TARGET_PROPERTY:GStreamer::GStreamer,INTERFACE_LINK_OPTIONS>
    )

    target_include_directories(
        GStreamerMobile
        INTERFACE
            $<TARGET_PROPERTY:GStreamer::GStreamer,INTERFACE_INCLUDE_DIRECTORIES>
    )

    # text relocations are strictly forbidden, error out if we encounter any
    if(DEFINED NEEDS_TEXTREL_ERROR)
        target_link_options(
            GStreamerMobile
            PRIVATE
                "-Wl,-z,text"
        )
    endif()

    # resolve textrels in the x86 asm
    if(DEFINED NEEDS_BSYMBOLIC_FIX)
        target_link_options(
            GStreamerMobile
            PRIVATE
                "-Wl,-Bsymbolic"
        )
    endif()

    check_ipo_supported(RESULT _gst_supports_lto LANGUAGES C CXX)
    if (_gst_supports_lto)
        set_property(TARGET GStreamerMobile
            PROPERTY
                INTERPROCEDURAL_OPTIMIZATION TRUE
        )
        if (APPLE)
            # https://gitlab.kitware.com/cmake/cmake/-/issues/25202
            target_link_options(GStreamerMobile PRIVATE
                "-Wl,-cache_path_lto,${CMAKE_CURRENT_BINARY_DIR}/lto.cache"
                "-Wl,-object_path_lto,$<TARGET_FILE:GStreamerMobile>.lto.o"
            )
        endif()
    elseif(ANDROID AND NOT CMAKE_ANDROID_NDK_VERSION)
        # https://github.com/android-ndk/ndk/issues/242
        message(WARNING "GStreamer::mobile can use LTO for trimming, please set -DANDROID_USE_LEGACY_TOOLCHAIN_FILE=OFF for better optimizations")
    endif()
    if (MSVC)
        target_compile_options(GStreamerMobile
            PRIVATE
                "/Gw"
        )
        target_link_options(GStreamerMobile
            PRIVATE
                "/OPT:REF"
        )
    endif()

    if (ANDROID)
        # Collect all Java-based initializer classes
        set(GSTREAMER_PLUGINS_CLASSES)
        foreach(LOCAL_PLUGIN IN LISTS GSTREAMER_PLUGINS)
            file(GLOB_RECURSE
                LOCAL_PLUGIN_CLASS
                FOLLOW_SYMLINKS
                RELATIVE "${GStreamer_NDK_BUILD_PATH}"
                "${GStreamer_NDK_BUILD_PATH}/${LOCAL_PLUGIN}/*.java"
            )
            list(APPEND GSTREAMER_PLUGINS_CLASSES ${LOCAL_PLUGIN_CLASS})
        endforeach()

        # Same as above, but collect the plugins themselves
        set(GSTREAMER_PLUGINS_WITH_CLASSES)
        foreach(LOCAL_PLUGIN IN LISTS GSTREAMER_PLUGINS)
            if(EXISTS "${GStreamer_NDK_BUILD_PATH}/${LOCAL_PLUGIN}/")
                list(APPEND GSTREAMER_PLUGINS_WITH_CLASSES ${LOCAL_PLUGIN})
            endif()
        endforeach()

        add_custom_target(
            "copyjavasource_${ANDROID_ABI}"
        )

        foreach(LOCAL_FILE IN LISTS GSTREAMER_PLUGINS_CLASSES)
            string(MAKE_C_IDENTIFIER "cp_${LOCAL_FILE}" COPYJAVASOURCE_TGT)
            add_custom_target(
                ${COPYJAVASOURCE_TGT}
                COMMAND
                    "${CMAKE_COMMAND}" -E make_directory
                    "${GStreamer_JAVA_SRC_DIR}/org/freedesktop/gstreamer/"
                COMMAND
                    "${CMAKE_COMMAND}" -E copy
                    "${GStreamer_NDK_BUILD_PATH}/${LOCAL_FILE}"
                    "${GStreamer_JAVA_SRC_DIR}/org/freedesktop/gstreamer/${LOCAL_FILE}"
                BYPRODUCTS
                    "${GStreamer_JAVA_SRC_DIR}/org/freedesktop/gstreamer/${LOCAL_FILE}"
            )
            add_dependencies(copyjavasource_${ANDROID_ABI} ${COPYJAVASOURCE_TGT})
        endforeach()
    endif()

    # And, finally, set the GIO modules up
    if (G_IO_MODULES)
        add_library(GStreamer::gio_modules INTERFACE IMPORTED)

        # Path for the static GIO modules
        set(_old_pkg_config_path "$ENV{PKG_CONFIG_PATH}")
        set(ENV{PKG_CONFIG_PATH} "${GStreamer_PKG_CONFIG_DIRS}")
        pkg_get_variable(G_IO_MODULES_PATH gio-2.0 giomoduledir)
        if (CMAKE_HOST_SYSTEM_NAME STREQUAL "Windows")
            set(ENV{PKG_CONFIG_PATH} "$ENV{PKG_CONFIG_PATH};${G_IO_MODULES_PATH}/pkgconfig")
        else()
            set(ENV{PKG_CONFIG_PATH} "$ENV{PKG_CONFIG_PATH}:${G_IO_MODULES_PATH}/pkgconfig")
        endif()

        # Path for the static GIO modules
        foreach(_gio_plugin IN LISTS G_IO_MODULES)
            pkg_check_modules(PC_GIO_${_gio_plugin} "gio${_gio_plugin}"
                IMPORTED_TARGET
                REQUIRED
            )
            if (GStreamer_USE_STATIC_LIBS AND NOT WIN32)
                _gst_apply_frameworks(PC_GIO_${_gio_plugin}_STATIC_LDFLAGS_OTHER GStreamer::gio_modules)
                # Handle all libraries, even those specified with -l:libfoo.a (srt)
                _gst_apply_link_libraries(OFF PC_GIO_${_gio_plugin}_STATIC_LIBRARIES PC_GIO_${_gio_plugin}_STATIC_LIBRARY_DIRS GStreamer::gio_modules)
                target_link_options(GStreamer::gio_modules
                    INTERFACE
                        $<TARGET_PROPERTY:PkgConfig::PC_GIO_${_gio_plugin},INTERFACE_LINK_OPTIONS>
                )
                target_include_directories(GStreamer::gio_modules
                    INTERFACE
                        $<TARGET_PROPERTY:PkgConfig::PC_GIO_${_gio_plugin},INTERFACE_INCLUDE_DIRECTORIES>
                )
            else()
                target_link_libraries(GStreamer::gio_modules INTERFACE 
                    PkgConfig::PC_GIO_${_gio_plugin}
                )
            endif()
        endforeach()

        target_link_libraries(
            GStreamerMobile
            PRIVATE
                GStreamer::gio_modules
        )
        set(ENV{PKG_CONFIG_PATH} "${_old_pkg_config_path}")
        unset(_old_pkg_config_path)
    endif()
    set(GStreamer_mobile_FOUND TRUE)
endif()

if(fonts IN_LIST GStreamerMobile_FIND_COMPONENTS)
    set(GStreamer_UBUNTU_R_TTF "${GStreamer_NDK_BUILD_PATH}/fontconfig/fonts/Ubuntu-R.ttf"
        CACHE FILEPATH "Path to Ubuntu-R.ttf"
    )
    set(GStreamer_FONTS_CONF
        "${GStreamer_NDK_BUILD_PATH}/fontconfig/fonts.conf"
        CACHE FILEPATH "Path to fonts.conf"
    )
    if (EXISTS "${GStreamer_UBUNTU_R_TTF}" AND EXISTS "${GStreamer_FONTS_CONF}")
        set(GStreamerMobile_fonts_FOUND ON)
        set(_gst_required_vars "GStreamer_UBUNTU_R_TTF GStreamer_FONTS_CONF ${gst_required_vars}")

        if (ANDROID)
            string(REPLACE "//copyFonts" "copyFonts" JAVA_INPUT "${JAVA_INPUT}")
            add_custom_target(
                copyfontsres_${ANDROID_ABI}
                COMMAND
                    "${CMAKE_COMMAND}" -E make_directory
                    "${GStreamer_ASSETS_DIR}/fontconfig/fonts/truetype/"
                COMMAND
                    "${CMAKE_COMMAND}" -E copy
                    "${GStreamer_UBUNTU_R_TTF}"
                    "${GStreamer_ASSETS_DIR}/fontconfig/fonts/truetype/"
                COMMAND
                    "${CMAKE_COMMAND}" -E copy
                    "${GStreamer_FONTS_CONF}"
                    "${GStreamer_ASSETS_DIR}/fontconfig/"
                BYPRODUCTS
                    "${GStreamer_ASSETS_DIR}/fontconfig/fonts/truetype/Ubuntu-R.ttf"
                    "${GStreamer_ASSETS_DIR}/fontconfig/fonts.conf"
            )

            if (TARGET GStreamerMobile)
                add_dependencies(GStreamerMobile copyfontsres_${ANDROID_ABI})
            endif()
        elseif(APPLE)
            set(GStreamerMobile_fonts_FOUND ON)
            list(APPEND GSTREAMER_RESOURCES "${GStreamer_FONTS_CONF}" "${GStreamer_UBUNTU_R_TTF}")
        else()
            message(FATAL_ERROR "No fonts assets available for this operating system.")
        endif()
    else()
        set(GStreamerMobile_fonts_FOUND OFF)
    endif()
endif()

if(ca_certificates IN_LIST GStreamerMobile_FIND_COMPONENTS)
    set(GStreamer_CA_BUNDLE "${GStreamer_ROOT_DIR}/etc/ssl/certs/ca-certificates.crt"
        CACHE FILEPATH "Path to ca-certificates bundle"
    )
    if (EXISTS "${GStreamer_CA_BUNDLE}")
        set(GStreamerMobile_ca_certificates_FOUND ON)
        string(REPLACE "//copyCaCertificates" "copyCaCertificates" JAVA_INPUT "${JAVA_INPUT}")
        set(_gst_required_vars "GStreamer_CA_BUNDLE ${_gst_required_vars}")

        if (ANDROID)
            add_custom_target(
                copycacertificatesres_${ANDROID_ABI}
                COMMAND
                    "${CMAKE_COMMAND}" -E make_directory
                    "${GStreamer_ASSETS_DIR}/ssl/certs/"
                COMMAND
                    "${CMAKE_COMMAND}" -E copy
                    "${GStreamer_CA_BUNDLE}"
                    "${GStreamer_ASSETS_DIR}/ssl/certs/"
                BYPRODUCTS "${GStreamer_ASSETS_DIR}/ssl/certs/ca-certificates.crt"
            )

            if (TARGET GStreamerMobile)
                add_dependencies(GStreamerMobile copycacertificatesres_${ANDROID_ABI})
                target_compile_definitions(GStreamerMobile
                    PRIVATE
                        GSTREAMER_INCLUDE_CA_CERTIFICATES
                )
            endif()
        elseif (APPLE)
            list(APPEND GSTREAMER_RESOURCES "${GStreamer_CA_BUNDLE}")
        else()
            message(FATAL_ERROR "No certificate bundle available for this operating system.")
        endif()
    else()
        set(GStreamerMobile_ca_certificates_FOUND OFF)
    endif()
endif()

if (ANDROID)
    file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/GStreamer.java" "${JAVA_INPUT}")
    add_custom_target(
        enable_includes_in_gstreamer_java
        COMMAND
            "${CMAKE_COMMAND}" -E make_directory
            "${GStreamer_JAVA_SRC_DIR}/org/freedesktop/gstreamer/"
        COMMAND
            "${CMAKE_COMMAND}" -E copy
            "${CMAKE_CURRENT_BINARY_DIR}/GStreamer.java"
            "${GStreamer_JAVA_SRC_DIR}/org/freedesktop/gstreamer/GStreamer.java"
        BYPRODUCTS
            "${GStreamer_JAVA_SRC_DIR}/org/freedesktop/gstreamer/GStreamer.java"
    )
    if (TARGET GStreamerMobile)
        add_dependencies(copyjavasource_${ANDROID_ABI} enable_includes_in_gstreamer_java)
        add_dependencies(GStreamerMobile copyjavasource_${ANDROID_ABI})
    endif()
endif()

if (TARGET GStreamerMobile AND GSTREAMER_RESOURCES)
    set_target_properties(
        GStreamerMobile
        PROPERTIES
            RESOURCE "${GSTREAMER_RESOURCES}"
    )
endif()

# Perform final validation
include(FindPackageHandleStandardArgs)
foreach(_gst_PLUGIN IN LISTS _gst_plugins)
    set(GStreamerMobile_${_gst_PLUGIN}_FOUND "${GStreamer_${_gst_PLUGIN}_FOUND}")

    if (TARGET GStreamerMobile AND GStreamer_${_gst_PLUGIN}_FOUND)
        target_include_directories(
            GStreamerMobile
            INTERFACE
                $<TARGET_PROPERTY:GStreamer::${_gst_PLUGIN},INTERFACE_INCLUDE_DIRECTORIES>
        )
        target_link_libraries(
            GStreamerMobile
            PRIVATE
                GStreamer::${_gst_PLUGIN}
        )
    endif()
endforeach()
if (GSTREAMER_IS_MOBILE)
    if (WIN32)
        find_package(Python REQUIRED)
        find_file(GStreamer_Mobile_MAKEDEF_PY "gstreamer_mobile_makedef.py" PATHS "${CMAKE_CURRENT_LIST_DIR}" REQUIRED)
    else()
        find_program(GStreamer_Mobile_MAKEDEF_PY "gstreamer_mobile_makedef.py" PATHS "${CMAKE_CURRENT_LIST_DIR}" REQUIRED)
    endif()

    set(_dump_args)
    if (WIN32)
        list(APPEND _dump_args --os win)
    elseif(APPLE)
        list(APPEND _dump_args --os darwin --prefix _)
    endif()
    if (NOT WIN32)
        list(APPEND _dump_args --extra=gst_init_static_plugins)
    endif()

    if (MSVC)
        find_program(DUMPBIN_EXE dumpbin REQUIRED)
        list(APPEND _dump_args --dumpbin "${DUMPBIN_EXE}")
    else()
        find_program(DUMPBIN_EXE nm REQUIRED)
        list(APPEND _dump_args --nm "${DUMPBIN_EXE}")
    endif()

    list(REMOVE_DUPLICATES GStreamer_Mobile_SYMBOLS)
    foreach(regex IN LISTS GStreamer_Mobile_SYMBOLS)
        list(APPEND _dump_args "--regex=${regex}")
    endforeach()

    foreach(_gst_PLUGIN IN LISTS GSTREAMER_APIS)
        # CMAKE_CROSSCOMPILING aka FindPkgConfig got the correct paths
        # all erased. We have to rebuild them. See _gst_find_library
        if (CMAKE_CROSSCOMPILING)
            foreach(_gst_lib IN LISTS PC_GStreamer_${_gst_PLUGIN}_LIBRARIES)
                string(MAKE_C_IDENTIFIER "_gst_${_gst_lib}" GST_LOCAL_LIB)
                if (EXISTS "${${GST_LOCAL_LIB}}")
                    cmake_path(GET ${GST_LOCAL_LIB} FILENAME _gst_lib_filename)
                    if (_gst_lib_filename MATCHES "^(gst|libgst)")
                        list(APPEND _gst_libraries "${${GST_LOCAL_LIB}}")
                    endif()
                endif()
            endforeach()
            unset(GST_LOCAL_LIB)
        else()
            foreach (_gst_lib IN LISTS PC_GStreamer_${_gst_PLUGIN}_LINK_LIBRARIES)
                cmake_path(GET _gst_lib FILENAME _gst_lib_filename)
                if (_gst_lib_filename MATCHES "^(gst|libgst)")
                    list(APPEND _gst_libraries "${_gst_lib}")
                endif()
            endforeach()
        endif()
        unset(_gst_lib_filename)
        unset(_gst_lib)
    endforeach()
    unset(_gst_PLUGIN)

    list(REMOVE_DUPLICATES _gst_libraries)

    # ELF platforms do not allow exporting unused functions
    # unless the relevant objects have been wholearchived first
    # This is supplied by PC_GStreamer_LIBRARIES
    # and the relevant GSTREAMER_APIS entries above
    if (ANDROID)
        foreach(_gst_lib IN LISTS _gst_libraries)
            target_link_libraries(GStreamerMobile PRIVATE
                "-Wl,--whole-archive,${_gst_lib},--no-whole-archive"
            )
        endforeach()
        get_target_property(_gst_dedup GStreamerMobile LINK_LIBRARIES)
        # Prevent visibility inconsistencies between gstreamer-1.0
        # instances (there can be no more than one wholearchive)
        list(REMOVE_DUPLICATES _gst_dedup)
        set_target_properties(GStreamerMobile
            PROPERTIES 
                LINK_LIBRARIES "${_gst_dedup}"
        )
    endif()

    if (NOT DEFINED GStreamer_Mobile_MODULE_DEF)
        set(GStreamer_Mobile_MODULE_DEF "${GStreamer_Mobile_MODULE_NAME}.def")
    endif()

    # Do not pass | (pipe) as the regex parameter, CMake does
    # not quote the parameter and the shell will think it's a
    # redirection operator
    if (EXISTS "${GStreamer_Mobile_MODULE_DEF}")
        message(STATUS "${GStreamer_Mobile_MODULE_DEF} exists, skipping GStreamer .def generation.")
    else()
        message(STATUS "Generating ${GStreamer_Mobile_MODULE_DEF}.")
        add_custom_target(gstreamermobiledef
            COMMENT "Generating module definition file"
            COMMAND
                ${Python_EXECUTABLE}
                ${GStreamer_Mobile_MAKEDEF_PY}
                -o "${GStreamer_Mobile_MODULE_DEF}"
                ${_dump_args}
                "--regex=[_]?[gG][sS][tT]_"
                ${_gst_libraries}
            BYPRODUCTS "${GStreamer_Mobile_MODULE_DEF}"
            COMMAND_EXPAND_LISTS
        )
        add_dependencies(GStreamerMobile gstreamermobiledef)
    endif()

    if (WIN32)
        target_sources(GStreamerMobile PRIVATE "${GStreamer_Mobile_MODULE_DEF}")
    elseif(APPLE)
        target_link_options(GStreamerMobile PRIVATE 
            "-Wl,-exported_symbols_list,${GStreamer_Mobile_MODULE_DEF}"
        )
    else()
        target_link_options(GStreamerMobile PRIVATE 
            "-Wl,--version-script,${GStreamer_Mobile_MODULE_DEF}"
        )
    endif()

    unset(_dump_args)
    unset(_gst_libraries)
endif()
# FIXME: CMake does not tolerate interpolation of REQUIRED_VARS
find_package_handle_standard_args(GStreamerMobile
    HANDLE_COMPONENTS
)
