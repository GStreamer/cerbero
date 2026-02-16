This is a complete Python "distribution" of GStreamer for Python apps and SDKs
to use, including the Python bindings and all libraries and plugins that we
ship with our installers on macOS and Windows. These components are split
across multiple dependent wheels, and this package pulls all of them.

It is common for end-user applications to pick-and-choose plugins and libraries
to bundle, or statically link to them.
