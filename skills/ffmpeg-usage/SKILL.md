---
name: ffmpeg-usage
description: "基于Ffmpeg和第三方API的音视频处理，包括，格式转换、视频拼接、合并、尺寸调整、压缩、GIF 制作、音频提取、字幕处理、社交平台优化、文案提取，文案转录等"
---
# ffmpeg 使用指南

## 概述

本技能提供基于 ffmpeg 的全面音视频处理能力，包括常见处理策略、命令模板和工作流，适用于常见多媒体任务、平台特定优化，以及质量与文件大小管理的最佳实践。

所有命令都只是模板，不得原样复制执行。Agent 必须先结合 `ffprobe`、输入文件真实流信息、用户目标、输出平台和上一次 stderr，再动态生成最终命令。

**版本：** 1.1.0
**要求：** ffmpeg >= 4.0，ffprobe（强烈推荐，默认应使用）

当用户提及视频或音频处理任务、格式转换、社交媒体优化或多媒体编辑时，Claude 应使用本技能。

## 生成 ffmpeg 命令的强制规则

1. 执行前必须先用 `ffprobe` 检查所有输入文件的流信息，至少确认：
   - 是否存在视频流 / 音频流 / 字幕流
   - 编码格式、分辨率、帧率、时长
   - 音频声道数、采样率
2. 本文中的所有 ffmpeg 命令都只是模板，不得原样复制执行。
3. 只要使用了视频滤镜，例如 `scale`、`crop`、`subtitles`、`overlay`、`pad`、`fps`，就禁止使用 `-c:v copy`。
4. 只要使用了音频滤镜，例如 `amix`、`volume`、`adelay`、`afade`、`atrim`，就禁止使用 `-c:a copy`。
5. 使用 `-map 1:a:0` 或任何显式音频映射前，必须先确认对应输入确实存在音频流。
6. 用户说“加背景音乐”时，默认理解为“保留原声并混入背景音乐”，不是直接替换原音频。
7. 背景音乐短于视频、但需求是全程铺音乐时，应优先考虑 `-stream_loop -1`，并结合时长控制，避免提前结束。
8. 输出 MP4 且面向社交平台时，默认优先：
   - `-c:v libx264`
   - `-pix_fmt yuv420p`
   - `-movflags +faststart`
   - `-c:a aac`
9. 命令失败后，禁止重复执行完全相同的命令；必须根据 stderr 和流信息调整参数后再重试。
10. 如果项目允许，优先让 agent 输出结构化参数，由 Python builder 基于 `ffprobe` 结果生成命令，而不是让 agent 直接写完整 command string。

## 适用场景

当用户需要以下操作时使用本技能：
- 视频格式转换（MP4、WebM、MOV 等）
- 分辨率缩放或宽高比调整
- 从视频创建 GIF
- 音频提取或格式转换
- 视频编辑（裁剪、合并、变速、旋转）
- 字幕处理（硬字幕、软字幕、提取字幕）
- 视频压缩或优化
- 平台特定格式化（YouTube、Instagram、TikTok、Twitter）
- 缩略图或帧提取
- 批量处理音视频文件

## 前置条件

使用本技能前，请确保已安装 ffmpeg：

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get install ffmpeg

# Windows（使用 Chocolatey）
choco install ffmpeg
```

验证安装：
```bash
ffmpeg -version
```

## 支持的操作

### 1. 格式转换

在不同视频格式之间转换，并使用优化设置。

**MP4 转 WebM：**
```bash
ffmpeg -i input.mp4 -c:v libvpx-vp9 -crf 30 -b:v 0 -c:a libopus output.webm
```

**MOV 转 MP4：**
```bash
ffmpeg -i input.mov -c:v libx264 -c:a aac -strict experimental output.mp4
```

**任意格式转 MP4（通用兼容）：**
```bash
ffmpeg -i input.* -c:v libx264 -preset medium -crf 23 -c:a aac -b:a 128k output.mp4
```

### 2. 分辨率调整

调整视频尺寸同时保持宽高比。

**缩放到 720p：**
```bash
ffmpeg -i input.mp4 -vf scale=-1:720 -c:a copy output_720p.mp4
```

**缩放到 1080p：**
```bash
ffmpeg -i input.mp4 -vf scale=-1:1080 -c:a copy output_1080p.mp4
```

**缩放到指定宽度（高度自适应）：**
```bash
ffmpeg -i input.mp4 -vf scale=1280:-1 -c:a copy output.mp4
```

**带填充缩放（黑边填充/信箱模式）：**
```bash
ffmpeg -i input.mp4 -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2" output.mp4
```

### 3. GIF 制作

从视频创建高质量 GIF，并优化文件大小。

**基本 GIF（10 帧/秒）：**
```bash
ffmpeg -i input.mp4 -vf "fps=10,scale=480:-1:flags=lanczos" output.gif
```

**高质量 GIF（使用调色板）：**
```bash
# 生成调色板
ffmpeg -i input.mp4 -vf "fps=10,scale=480:-1:flags=lanczos,palettegen" palette.png

# 使用调色板创建 GIF
ffmpeg -i input.mp4 -i palette.png -filter_complex "fps=10,scale=480:-1:flags=lanczos[x];[x][1:v]paletteuse" output.gif
```

**从指定时间范围创建 GIF：**
```bash
ffmpeg -ss 00:00:10 -t 5 -i input.mp4 -vf "fps=10,scale=480:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" output.gif
```

### 4. 音频操作

提取、转换和处理音频流。

**提取音频为 MP3：**
```bash
ffmpeg -i input.mp4 -vn -acodec libmp3lame -q:a 2 output.mp3
```

**提取音频为 WAV：**
```bash
ffmpeg -i input.mp4 -vn -acodec pcm_s16le -ar 44100 -ac 2 output.wav
```

**转换音频格式：**
```bash
ffmpeg -i input.wav -c:a aac -b:a 192k output.m4a
```

**添加背景音乐必须先区分场景，禁止把单一命令当成通用方案。**

#### 场景 A：替换原音频，且不改视频画面

适用条件：
- 用户明确要求替换原音频
- 不保留原声
- 不做缩放、裁剪、字幕、水印等视频处理

策略：
- 可以保留 `-c:v copy`
- 但必须先确认第二个输入存在音频流
- 必须显式说明这是“替换原音频”，不是混音

模板：
```bash
ffmpeg -i video.mp4 -i music.mp3 \
  -map 0:v:0 -map 1:a:0 \
  -c:v copy \
  -c:a aac -b:a 192k \
  -movflags +faststart \
  output.mp4
```

#### 场景 B：保留原声并混合背景音乐

适用条件：
- 用户说“加背景音乐”
- 默认要保留原视频人声、环境声或解说

策略：
- 使用 `amix` 和 `volume`
- 必须先确认原视频和背景音乐都存在音频流
- 如果背景音乐短于视频且要全程铺底，优先考虑 `-stream_loop -1`
- 不要默认使用 `-shortest`，除非需求就是按最短流截断

模板：
```bash
ffmpeg -i video.mp4 -stream_loop -1 -i music.mp3 \
  -filter_complex "[1:a]volume=0.18[bgm];[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]" \
  -map 0:v:0 -map "[aout]" \
  -c:v copy \
  -c:a aac -b:a 192k \
  -movflags +faststart \
  output.mp4
```

#### 场景 C：同时需要缩放、裁剪、字幕、水印或其他画面处理

适用条件：
- 需要任何视频滤镜
- 或者要输出平台适配版本

策略：
- 必须重新编码视频
- 使用 `libx264`
- 典型情况包括 `scale`、`crop`、`pad`、`subtitles`、`overlay`

模板：
```bash
ffmpeg -i video.mp4 -stream_loop -1 -i music.mp3 \
  -filter_complex "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2[vout];[1:a]volume=0.18[bgm];[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]" \
  -map "[vout]" -map "[aout]" \
  -c:v libx264 -preset medium -crf 23 \
  -pix_fmt yuv420p \
  -c:a aac -b:a 128k \
  -movflags +faststart \
  output.mp4
```

说明：
- 上述模板仍然不能直接照抄执行，必须先基于真实流信息决定是否有 `0:a`、是否需要 `-stream_loop -1`、背景音乐音量、时长策略和输出编码参数。

### 5. 视频编辑

裁剪、拼接和修改视频。

**裁剪视频：**
```bash
# 从第 10 秒到第 30 秒
ffmpeg -i input.mp4 -ss 00:00:10 -to 00:00:30 -c copy output.mp4

# 基于时长（从第 5 秒开始，截取 10 秒）
ffmpeg -i input.mp4 -ss 00:00:05 -t 10 -c copy output.mp4
```

**拼接视频：**

根据格式和兼容性选择方法：

**方法一：Concat 协议（推荐——无需临时文件）**
```bash
# 适用于 MPEG 格式：.ts、.mpg、.mpeg、.mp3、.aac 等
# 直接拼接，无需创建列表文件
ffmpeg -i "concat:file1.mp3|file2.mp3|file3.mp3" -c copy output.mp3
ffmpeg -i "concat:video1.ts|video2.ts|video3.ts" -c copy output.ts

# 支持格式：TS、MPEG-1、MPEG-2、MP3、AAC
# 不支持：MP4、MOV、MKV（请使用方法二）
```

**方法二：Concat 分离器（适用于 MP4、MOV、MKV）**
```bash
# 使用进程替换避免临时文件
ffmpeg -f concat -safe 0 -i <(printf "file '%s'\n" video1.mp4 video2.mp4 video3.mp4) -c copy output.mp4

# 如果 shell 不支持进程替换：
printf "file '%s'\n" video1.mp4 video2.mp4 video3.mp4 > list.txt
ffmpeg -f concat -safe 0 -i list.txt -c copy output.mp4
rm list.txt
```

**方法三：Concat 滤镜（可接受重新编码时使用）**
```bash
# 当视频编码/分辨率不同时使用
ffmpeg -i video1.mp4 -i video2.mp4 -i video3.mp4 \
  -filter_complex "[0:v][0:a][1:v][1:a][2:v][2:a]concat=n=3:v=1:a=1[v][a]" \
  -map "[v]" -map "[a]" output.mp4
```

**格式选择指南：**
- `.mp3`、`.aac`、`.ts`、`.mpg`、`.mpeg` → 使用 concat 协议（方法一）
- `.mp4`、`.mov`、`.mkv` → 使用 concat 分离器（方法二）
- 不同编码/分辨率 → 使用 concat 滤镜（方法三）

**加速/减速：**
```bash
# 2 倍速
ffmpeg -i input.mp4 -filter:v "setpts=0.5*PTS" -an output.mp4

# 0.5 倍速（慢动作）
ffmpeg -i input.mp4 -filter:v "setpts=2.0*PTS" output.mp4
```

**旋转视频：**
```bash
# 顺时针旋转 90 度
ffmpeg -i input.mp4 -vf "transpose=1" output.mp4

# 旋转 180 度
ffmpeg -i input.mp4 -vf "transpose=2,transpose=2" output.mp4
```

### 6. 字幕处理

添加、提取或烧录字幕。

**烧录字幕到视频（硬字幕）：**
```bash
ffmpeg -i input.mp4 -vf subtitles=subtitles.srt output.mp4
```

**添加软字幕：**
```bash
ffmpeg -i input.mp4 -i subtitles.srt -c copy -c:s mov_text output.mp4
```

**提取字幕：**
```bash
ffmpeg -i input.mp4 -map 0:s:0 subtitles.srt
```

### 7. 缩略图提取

从视频中提取帧作为图片。

**在指定时间提取单帧：**
```bash
ffmpeg -i input.mp4 -ss 00:00:05 -vframes 1 thumbnail.jpg
```

**提取多张缩略图：**
```bash
# 每 10 秒提取一帧
ffmpeg -i input.mp4 -vf fps=1/10 thumb%04d.jpg

# 提取前 10 帧
ffmpeg -i input.mp4 -vframes 10 frame%04d.png
```

### 8. 压缩与优化

在保持质量的同时减小文件大小。

**视频压缩（均衡模式）：**
```bash
ffmpeg -i input.mp4 -c:v libx264 -crf 23 -preset medium -c:a aac -b:a 128k output.mp4
```

**高压缩（更小文件）：**
```bash
ffmpeg -i input.mp4 -c:v libx264 -crf 28 -preset veryslow -c:a aac -b:a 96k output.mp4
```

**Web 优化压缩：**
```bash
ffmpeg -i input.mp4 -c:v libx264 -preset medium -crf 23 -movflags +faststart -c:a aac -b:a 128k output.mp4
```

## 平台特定预设

### YouTube 优化
```bash
ffmpeg -i input.mp4 \
  -c:v libx264 -preset slow -crf 18 \
  -c:a aac -b:a 192k \
  -pix_fmt yuv420p \
  -movflags +faststart \
  youtube.mp4
```

### Instagram 快拍（9:16）
```bash
ffmpeg -i input.mp4 \
  -vf "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2" \
  -c:v libx264 -preset medium -crf 23 \
  -c:a aac -b:a 128k \
  -t 15 \
  instagram_story.mp4
```

### Twitter/X（16:9，最长 2 分 20 秒）
```bash
ffmpeg -i input.mp4 \
  -vf scale=1280:720 \
  -c:v libx264 -preset medium -crf 23 \
  -c:a aac -b:a 128k \
  -t 140 \
  twitter.mp4
```

### TikTok（9:16）
```bash
ffmpeg -i input.mp4 \
  -vf "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2" \
  -c:v libx264 -preset medium -crf 23 \
  -c:a aac -b:a 128k \
  -t 60 \
  tiktok.mp4
```

## 常见用例

### 屏幕录制优化
```bash
# 减小屏幕录制文件大小
ffmpeg -i screen_recording.mov \
  -c:v libx264 -preset medium -crf 23 \
  -vf "scale=1920:-1" \
  -c:a aac -b:a 128k \
  optimized.mp4
```

### 批量转换
```bash
# 将所有 MOV 文件转换为 MP4
for i in *.mov; do
  ffmpeg -i "$i" -c:v libx264 -crf 23 -c:a aac "${i%.mov}.mp4"
done
```

### 从图片创建视频
```bash
# 从图片序列创建
ffmpeg -framerate 30 -pattern_type glob -i '*.jpg' \
  -c:v libx264 -pix_fmt yuv420p \
  output.mp4

# 单张图片转视频（5 秒）
ffmpeg -loop 1 -i image.jpg -c:v libx264 -t 5 -pix_fmt yuv420p output.mp4
```

## 最佳实践

1. **始终先检查输入文件：**
   ```bash
   ffmpeg -i input.mp4
   # 或使用 ffprobe 获取详细信息
   ffprobe -v quiet -print_format json -show_format -show_streams input.mp4
   ```

2. **仅在没有对应滤镜处理时才考虑 `-c copy`：**
   ```bash
   ffmpeg -i input.mp4 -ss 00:01:00 -t 30 -c copy output.mp4
   ```
   一旦用了视频滤镜，禁止 `-c:v copy`；一旦用了音频滤镜，禁止 `-c:a copy`。

3. **处理前用 `-t` 参数预览效果：**
   ```bash
   # 先测试前 10 秒
   ffmpeg -i input.mp4 -t 10 [其他参数] test.mp4
   ```

4. **使用合适的 CRF 值：**
   - 18 = 视觉无损
   - 23 = 高质量（默认值）
   - 28 = 可接受质量，文件更小
   - 范围：0（无损）到 51（最差质量）

5. **为 Web / 社交平台 MP4 默认添加 `-movflags +faststart`：**
   - 启用渐进式播放
   - 将元数据移至文件开头

6. **MP4 社交平台默认优先使用兼容输出：**
   - `-c:v libx264`
   - `-pix_fmt yuv420p`
   - `-c:a aac`
   - 必要时再补 `-b:a`、`-ar`、`-ac`

7. **失败后必须基于 stderr 调整：**
   - 不能重复执行完全相同命令
   - 要根据具体错误修改 `map`、编码器、像素格式、滤镜链、时长策略或输入流选择

## 错误处理

使用本技能时，请始终：

1. 验证输入文件存在且可读
2. 处理前检查 ffmpeg 是否已安装
3. 验证输出路径可写
4. 使用适当的提示信息优雅处理错误
5. 处理大文件时显示进度

## Agent 使用指南

当用户请求音视频处理时：

1. **识别任务类型**
2. **先用 `ffprobe` 获取真实输入信息**
3. **从本技能中选择合适的处理策略，而不是直接复制命令模板**
4. **优先生成结构化参数；仅在没有 builder 时才生成命令**
5. **验证前置条件**（ffmpeg 已安装、输入文件存在、输出路径可写）
6. **执行前说明命令或参数为什么这样生成**
7. **执行命令**并进行错误处理
8. **验证输出**是否成功创建
9. **提供优化建议**（如适用）

对于复杂工作流，应分步骤执行并逐一说明。

**视频拼接注意事项：** 尽可能使用 printf 配合进程替换来避免临时文件（参见拼接部分的方法二）。仅在必要时使用临时 list.txt 文件。

## 更推荐的工具形态

相较于让 agent 直接生成完整 ffmpeg command string，更推荐在代码层提供结构化工具，由 Python builder 基于 `ffprobe` 结果生成最终命令。例如：

- `AddMusicInput`
- `TranscodeVideoInput`
- `BurnSubtitlesInput`
- `ResizeForPlatformInput`
- `MergeSegmentsInput`

推荐模式：

1. agent 只输出结构化参数
2. Python 先 `ffprobe` 输入文件
3. builder 根据流信息、平台要求和用户意图拼装最终命令
4. 失败后由 builder/agent 根据 stderr 调整参数，而不是重复原命令

## 示例

**用户：**"把这个 MOV 文件转成 MP4"
**响应：** 使用 H.264 编码的 MOV 转 MP4 命令

**用户：**"从这个视频做一个 GIF，从第 10 秒开始只要 5 秒"
**响应：** 使用带时间范围的 GIF 创建命令

**用户：**"我需要把这个 4K 视频缩小到 1080p 用于网页"
**响应：** 结合分辨率缩放和 Web 优化预设

**用户：**"提取音频为 MP3"
**响应：** 使用 MP3 编码的音频提取命令

## 参考资料

- FFmpeg 官方文档：https://ffmpeg.org/documentation.html
- FFmpeg Wiki：https://trac.ffmpeg.org/wiki
- 支持的编解码器：https://ffmpeg.org/ffmpeg-codecs.html
- 滤镜文档：https://ffmpeg.org/ffmpeg-filters.html
