project(Worklets)
cmake_minimum_required(VERSION 3.16)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

set(CMAKE_CXX_STANDARD 20)

# Consume shared libraries and headers from prefabs
find_package(fbjni REQUIRED CONFIG)
find_package(ReactAndroid REQUIRED CONFIG)
find_package(hermes-engine REQUIRED CONFIG)

# default CMAKE_CXX_FLAGS: "-g -DANDROID -fdata-sections -ffunction-sections
# -funwind-tables -fstack-protector-strong -no-canonical-prefixes
# -D_FORTIFY_SOURCE=2 -Wformat -Werror=format-security -fstack-protector-all"
include("${REACT_NATIVE_DIR}/ReactAndroid/cmake-utils/folly-flags.cmake")
add_compile_options(${folly_FLAGS})

string(APPEND CMAKE_CXX_FLAGS " -DWORKLETS_VERSION=${WORKLETS_VERSION}\
    -DWORKLETS_FEATURE_FLAGS=\"${WORKLETS_FEATURE_FLAGS}\"")

# HERMES_V1_ENABLED is centralized in react-native-flags.cmake. Reference the
# value so CMake records it as used, otherwise it warns: "Manually-specified
# variables were not used by the project: HERMES_V1_ENABLED"
set(HERMES_V1_ENABLED "${HERMES_V1_ENABLED}")

string(APPEND CMAKE_CXX_FLAGS " -fno-omit-frame-pointer -fstack-protector-all")

if(${WORKLETS_PROFILING})
  string(APPEND CMAKE_CXX_FLAGS " -DWORKLETS_PROFILING")
endif()
if(${IS_REANIMATED_EXAMPLE_APP})
  string(APPEND CMAKE_CXX_FLAGS " -DIS_REANIMATED_EXAMPLE_APP -Wpedantic")
endif()

if(NOT ${CMAKE_BUILD_TYPE} MATCHES "Debug")
  string(APPEND CMAKE_CXX_FLAGS " -DNDEBUG")
endif()

set(BUILD_DIR "${CMAKE_SOURCE_DIR}/build")
set(ANDROID_CPP_DIR "${CMAKE_SOURCE_DIR}/src/main/cpp")
set(COMMON_CPP_DIR "${CMAKE_SOURCE_DIR}/../Common/cpp")

# Explicit source lists (replaces file(GLOB) to avoid Windows CMake reconfigure loop)
set(WORKLETS_COMMON_CPP_SOURCES
    ${COMMON_CPP_DIR}/worklets/AnimationFrameQueue/AnimationFrameBatchinator.cpp
    ${COMMON_CPP_DIR}/worklets/Compat/StableApi.cpp
    ${COMMON_CPP_DIR}/worklets/NativeModules/JSIWorkletsModuleProxy.cpp
    ${COMMON_CPP_DIR}/worklets/NativeModules/WorkletsModuleProxy.cpp
    ${COMMON_CPP_DIR}/worklets/NativeModules/WorkletsModuleProxyInitializer.cpp
    ${COMMON_CPP_DIR}/worklets/Networking/Networking.cpp
    ${COMMON_CPP_DIR}/worklets/Networking/NetworkingInstaller.cpp
    ${COMMON_CPP_DIR}/worklets/Networking/TextDecoding.cpp
    ${COMMON_CPP_DIR}/worklets/Registries/WorkletRuntimeRegistry.cpp
    ${COMMON_CPP_DIR}/worklets/RunLoop/AsyncQueueImpl.cpp
    ${COMMON_CPP_DIR}/worklets/RunLoop/EventLoop.cpp
    ${COMMON_CPP_DIR}/worklets/SharedItems/MemoryManager.cpp
    ${COMMON_CPP_DIR}/worklets/SharedItems/Shareable.cpp
    ${COMMON_CPP_DIR}/worklets/SharedItems/SynchronizableAccess.cpp
    ${COMMON_CPP_DIR}/worklets/SharedItems/SynchronizableDynamic.cpp
    ${COMMON_CPP_DIR}/worklets/SharedItems/SynchronizableFixed.cpp
    ${COMMON_CPP_DIR}/worklets/SharedItems/Serializable/CustomSerializable.cpp
    ${COMMON_CPP_DIR}/worklets/SharedItems/Serializable/Serializable.cpp
    ${COMMON_CPP_DIR}/worklets/SharedItems/Serializable/SerializableArray.cpp
    ${COMMON_CPP_DIR}/worklets/SharedItems/Serializable/SerializableArrayBuffer.cpp
    ${COMMON_CPP_DIR}/worklets/SharedItems/Serializable/SerializableBigInt.cpp
    ${COMMON_CPP_DIR}/worklets/SharedItems/Serializable/SerializableError.cpp
    ${COMMON_CPP_DIR}/worklets/SharedItems/Serializable/SerializableHostFunction.cpp
    ${COMMON_CPP_DIR}/worklets/SharedItems/Serializable/SerializableHostObject.cpp
    ${COMMON_CPP_DIR}/worklets/SharedItems/Serializable/SerializableImport.cpp
    ${COMMON_CPP_DIR}/worklets/SharedItems/Serializable/SerializableMap.cpp
    ${COMMON_CPP_DIR}/worklets/SharedItems/Serializable/SerializableObject.cpp
    ${COMMON_CPP_DIR}/worklets/SharedItems/Serializable/SerializableRegExp.cpp
    ${COMMON_CPP_DIR}/worklets/SharedItems/Serializable/SerializableRemoteFunction.cpp
    ${COMMON_CPP_DIR}/worklets/SharedItems/Serializable/SerializableScalar.cpp
    ${COMMON_CPP_DIR}/worklets/SharedItems/Serializable/SerializableSet.cpp
    ${COMMON_CPP_DIR}/worklets/SharedItems/Serializable/SerializableString.cpp
    ${COMMON_CPP_DIR}/worklets/SharedItems/Serializable/SerializableTurboModuleLike.cpp
    ${COMMON_CPP_DIR}/worklets/SharedItems/Serializable/SerializableWorklet.cpp
    ${COMMON_CPP_DIR}/worklets/Tools/FeatureFlags.cpp
    ${COMMON_CPP_DIR}/worklets/Tools/JSISerializer.cpp
    ${COMMON_CPP_DIR}/worklets/Tools/JSLogger.cpp
    ${COMMON_CPP_DIR}/worklets/Tools/JSScheduler.cpp
    ${COMMON_CPP_DIR}/worklets/Tools/UIScheduler.cpp
    ${COMMON_CPP_DIR}/worklets/Tools/VersionUtils.cpp
    ${COMMON_CPP_DIR}/worklets/Tools/WorkletsJSIUtils.cpp
    ${COMMON_CPP_DIR}/worklets/Tools/WorkletsVersion.cpp
    ${COMMON_CPP_DIR}/worklets/WorkletRuntime/HermesProfiling.cpp
    ${COMMON_CPP_DIR}/worklets/WorkletRuntime/RNRuntimeWorkletDecorator.cpp
    ${COMMON_CPP_DIR}/worklets/WorkletRuntime/RuntimeManager.cpp
    ${COMMON_CPP_DIR}/worklets/WorkletRuntime/UIRuntimeDecorator.cpp
    ${COMMON_CPP_DIR}/worklets/WorkletRuntime/WorkletHermesRuntime.cpp
    ${COMMON_CPP_DIR}/worklets/WorkletRuntime/WorkletRuntime.cpp
    ${COMMON_CPP_DIR}/worklets/WorkletRuntime/WorkletRuntimeDecorator.cpp
)

set(WORKLETS_ANDROID_CPP_SOURCES
    ${ANDROID_CPP_DIR}/worklets/android/AndroidUIScheduler.cpp
    ${ANDROID_CPP_DIR}/worklets/android/JScriptBufferWrapper.cpp
    ${ANDROID_CPP_DIR}/worklets/android/PlatformLogger.cpp
    ${ANDROID_CPP_DIR}/worklets/android/WorkletsModule.cpp
    ${ANDROID_CPP_DIR}/worklets/android/WorkletsOnLoad.cpp
    ${ANDROID_CPP_DIR}/worklets/android/networking/AndroidNetworkingBackend.cpp
    ${ANDROID_CPP_DIR}/worklets/android/networking/JNetworkRequestListener.cpp
)

add_library(worklets SHARED ${WORKLETS_COMMON_CPP_SOURCES}
                            ${WORKLETS_ANDROID_CPP_SOURCES})

target_precompile_headers(worklets PRIVATE "${ANDROID_CPP_DIR}/WorkletsPCH.h")

# Stop Clang from embedding a build timestamp in the .pch. Without this the PCH
# is non-reproducible across builds, so ccache can't reuse it and translation
# units reject a restored PCH as "modified since built".
target_compile_options(
  worklets PRIVATE "$<$<COMPILE_LANGUAGE:CXX>:-Xclang;-fno-pch-timestamp>")

include("${REACT_NATIVE_DIR}/ReactCommon/cmake-utils/react-native-flags.cmake")
target_compile_reactnative_options(worklets PUBLIC)

# includes
target_include_directories(worklets PUBLIC "${COMMON_CPP_DIR}"
                                           "${ANDROID_CPP_DIR}")

target_include_directories(
  worklets
  PRIVATE "${REACT_NATIVE_DIR}/ReactCommon"
          "${REACT_NATIVE_DIR}/ReactCommon/yoga"
          "${REACT_NATIVE_DIR}/ReactAndroid/src/main/jni/react/turbomodule"
          "${REACT_NATIVE_DIR}/ReactCommon/react/nativemodule/core/ReactCommon"
          "${REACT_NATIVE_DIR}/ReactCommon/callinvoker"
          "${REACT_NATIVE_DIR}/ReactCommon/runtimeexecutor"
          "${REACT_NATIVE_DIR}/ReactCommon/jsiexecutor"
          "${REACT_NATIVE_DIR}/ReactCommon/react/renderer/graphics/platform/cxx"
)

# build shared lib
set_target_properties(worklets PROPERTIES LINKER_LANGUAGE CXX)

target_link_libraries(worklets android log ReactAndroid::reactnative
                      ReactAndroid::jsi fbjni::fbjni)

target_link_libraries(worklets hermes-engine::hermesvm)

if(${HERMES_ENABLE_DEBUGGER})
  string(APPEND CMAKE_CXX_FLAGS " -DHERMES_ENABLE_DEBUGGER=1")
endif()