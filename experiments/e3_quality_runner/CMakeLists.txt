cmake_minimum_required(VERSION 3.27)

project(e3-quality-runner LANGUAGES C CXX ASM)

if(NOT DEFINED LLM_RUNNER_SOURCE_DIR)
    message(FATAL_ERROR "LLM_RUNNER_SOURCE_DIR must point to Arm LLM-Runner")
endif()

add_subdirectory("${LLM_RUNNER_SOURCE_DIR}" llm-runner)

add_executable(e3-quality-cli main.cpp)
target_compile_features(e3-quality-cli PRIVATE cxx_std_17)
target_link_libraries(e3-quality-cli PRIVATE llm-cpp)
