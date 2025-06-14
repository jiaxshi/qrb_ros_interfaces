cmake_minimum_required(VERSION 3.5)
project(qrb_ros_amr_msgs)

# Default to C99
if(NOT CMAKE_C_STANDARD)
  set(CMAKE_C_STANDARD 99)
endif()

# Default to C++141
if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 14)
endif()

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(std_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "action/Cmd.action"
  "action/AE.action"
  "msg/AMRStatus.msg"
  "msg/WheelStatus.msg"
  "msg/Exception.msg"
  "msg/BatteryInfo.msg"
  "srv/API.srv"
  "srv/SubCmd.srv"
  "srv/Mapping.srv"
  DEPENDENCIES nav_msgs geometry_msgs std_msgs)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
