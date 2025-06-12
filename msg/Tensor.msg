# Copyright (c) 2024 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause-Clear

# name of tensor
string name

# type of tensor data
# 0: "uint8"
# 1: "int8"
# 2: "float32"
# 3: "float64"
int32 data_type

# shape of tensor
uint32[] shape

# data buffer
uint8[] data