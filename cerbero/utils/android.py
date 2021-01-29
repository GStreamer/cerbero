from cerbero.enums import Architecture

def get_android_arch_name(target_arch):
    if target_arch == Architecture.ARMv7:
        arch_name = "armeabi-v7a"
    elif target_arch == Architecture.ARM:
        arch_name = "armeabi"
    elif target_arch == Architecture.ARM64:
        arch_name = "arm64-v8a"
    elif target_arch == Architecture.X86:
        arch_name = "x86"
    elif target_arch == Architecture.X86_64:
        arch_name = "x86_64"
    else:
        raise FatalError("Unsupported Android architecture: " + target_arch)

    return arch_name

