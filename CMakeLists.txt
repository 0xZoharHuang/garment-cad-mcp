cmake_minimum_required(VERSION 3.25)
project(garment-cad-mcp LANGUAGES CXX)

find_program(QBS_EXECUTABLE qbs)
if(QBS_EXECUTABLE)
  add_custom_target(
    valentina-guis
    COMMAND
      "${CMAKE_SOURCE_DIR}/scripts/build-valentina.sh"
    COMMAND
      "${CMAKE_SOURCE_DIR}/scripts/smoke-valentina-guis.sh"
    COMMAND
      "${CMAKE_SOURCE_DIR}/scripts/test-native-valentina.sh"
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    USES_TERMINAL
  )
else()
  message(WARNING "Qbs not found; install qbs before building Valentina/Tape/Puzzle")
endif()

add_custom_target(
  python-check
  COMMAND uv run scripts/generate-atomic-contracts.py --check
  COMMAND uv run ruff check src tests scripts
  COMMAND uv run pytest
  COMMAND "${CMAKE_SOURCE_DIR}/scripts/test-native-garmentcode.sh"
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  USES_TERMINAL
)
