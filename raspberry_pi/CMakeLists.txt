cmake_minimum_required(VERSION 3.10)
project(edgehub C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(SQLite3 REQUIRED)
find_package(Threads REQUIRED)

set(MONGOOSE_DIR ${CMAKE_SOURCE_DIR}/third_party/mongoose)

add_executable(edgehub
    main.cpp
    src/frame.cpp
    src/frame_parser.cpp
    src/epoll.cpp
    src/board_channel.cpp
    src/conn_mgr.cpp
    src/tcp_acceptor.cpp
    src/ws_server.cpp
    src/msg_router.cpp
    src/storage.cpp
    src/cmd_mgr.cpp
    src/rate_limiter.cpp
    ${MONGOOSE_DIR}/mongoose.c
)

target_include_directories(edgehub PRIVATE
    ${CMAKE_SOURCE_DIR}/include
    ${MONGOOSE_DIR}
)

target_link_libraries(edgehub PRIVATE
    SQLite::SQLite3
    Threads::Threads
)

target_compile_options(edgehub PRIVATE -Wall -Wextra -O2 -mcpu=cortex-a72)
