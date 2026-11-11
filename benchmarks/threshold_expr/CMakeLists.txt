file(MAKE_DIRECTORY ${CMAKE_BINARY_DIR}/benchmarks/threshold_expr/he)
add_executable(threshold_expr threshold_expr.cpp)
target_link_libraries(threshold_expr PRIVATE fheco)

# Files the generated SEAL program needs next to it (same as the other benchmarks).
# The dataset (threshold_benchmarks.txt) is copied by scripts/run_benchmarks_unified.py.
set(SRC_DIR ${CMAKE_SOURCE_DIR}/benchmarks)
set(DST_DIR ${CMAKE_SOURCE_DIR}/build/benchmarks/threshold_expr)
add_custom_target(copy_files_threshold_expr ALL
    COMMAND ${CMAKE_COMMAND} -E copy ${SRC_DIR}/utils.cpp ${DST_DIR}/he/utils.cpp
    COMMAND ${CMAKE_COMMAND} -E copy ${SRC_DIR}/utils.hpp ${DST_DIR}/he/utils.hpp
    COMMAND ${CMAKE_COMMAND} -E copy ${SRC_DIR}/threshold_expr/he/CMakeLists.txt ${DST_DIR}/he/CMakeLists.txt
    COMMAND ${CMAKE_COMMAND} -E copy ${SRC_DIR}/threshold_expr/fhe_io_example.txt ${DST_DIR}/fhe_io_example.txt
    COMMENT "Copying the SEAL program files of threshold_expr"
)
