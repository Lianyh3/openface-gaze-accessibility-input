# OpenFace 安装与验证记录

更新时间：2026-03-08

## 1. 源码与构建结果

1. 源码目录：`/home/lyh/workspace/OpenFace-OpenFace_2.2.0`
2. 构建目录：`/home/lyh/workspace/OpenFace-OpenFace_2.2.0/build_clean`
3. 关键可执行文件：
   - `build_clean/bin/FeatureExtraction`
   - `build_clean/bin/FaceLandmarkVid`
   - `build_clean/bin/FaceLandmarkVidMulti`
   - `build_clean/bin/FaceLandmarkImg`

## 2. 兼容性调整

在 Ubuntu 22.04 环境下，系统 dlib 版本为 `19.10.0`，原仓库 CMake 要求 `19.13` 会导致配置失败。  
已做最小改动：

1. 文件：`/home/lyh/workspace/OpenFace-OpenFace_2.2.0/CMakeLists.txt`
2. 改动：`find_package(dlib 19.13)` -> `find_package(dlib 19.10)`

## 3. 模型下载

已执行官方脚本：

```bash
cd /home/lyh/workspace/OpenFace-OpenFace_2.2.0
bash download_models.sh
```

由于 CEN 模型下载源在当前网络下不稳定，运行时使用 `main_clnf_wild.txt`（不依赖 CEN `.dat`）进行验证。

## 4. 已验证通过项

使用样例图像运行 `FeatureExtraction` 并成功导出 CSV：

```bash
cd /home/lyh/workspace/OpenFace-OpenFace_2.2.0/build_clean/bin
./FeatureExtraction \
  -mloc model/main_clnf_wild.txt \
  -f ../../samples/sample1.jpg \
  -out_dir /home/lyh/workspace/OpenFace-OpenFace_2.2.0/test_out
```

输出目录（存在）：

`/home/lyh/workspace/OpenFace-OpenFace_2.2.0/test_out`

其中包含：

1. `sample1.csv`
2. `sample1.avi`
3. `sample1.hog`
4. `sample1_aligned/`

## 5. 摄像头验证命令（你本机执行）

```bash
cd /home/lyh/workspace/OpenFace-OpenFace_2.2.0/build_clean/bin
./FeatureExtraction \
  -mloc model/main_clnf_wild.txt \
  -device 0 \
  -out_dir /home/lyh/workspace/OpenFace-OpenFace_2.2.0/test_cam
```

预期结果：

1. 程序可打开摄像头实时跟踪。
2. 结束后 `test_cam` 目录下生成 `*.csv`（包含 `gaze_0_x/y/z`、`gaze_1_x/y/z`、`pose_R*` 等字段）。

备注：当前自动化执行环境里不可见 `/dev/video0`，因此摄像头打开失败；这不是 OpenFace 编译问题。

