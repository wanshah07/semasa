#!/usr/bin/env bash
# ffmpeg and ffprobe on a GitHub runner without depending on apt (Wan, 11 Nov 2026: "apt-get update gagal dari GitHub
# runner ... guna imageio-ffmpeg"). ubuntu-latest no longer ships ffmpeg, and `apt-get update` from the runner fails often
# enough that films were rendered with "FFmpeg not found". The order, fastest and most dependable first:
#   1. already on PATH: nothing to do
#   2. ffmpeg from the imageio-ffmpeg wheel (PyPI, already in backend/requirements.txt) and ffprobe from the ffprobe-static
#      npm package: two registries every job here already reaches. Both are linked into /usr/local/bin under their own
#      names, because the worker and HyperFrames call `ffmpeg` and `ffprobe` by name. imageio-ffmpeg has no ffprobe.
#   3. apt, as the last resort, for whatever is still missing.
# It exits 0 even when something is still missing and says so loudly: the job's own checks decide what that means.
set -u
have() { command -v "$1" >/dev/null 2>&1 && "$1" -version >/dev/null 2>&1; }
link() {  # link <binary path> <name>
  [ -n "$1" ] && [ -f "$1" ] || return 1
  chmod +x "$1" 2>/dev/null || true
  sudo ln -sf "$1" "/usr/local/bin/$2" 2>/dev/null || { mkdir -p "$HOME/.local/bin" && ln -sf "$1" "$HOME/.local/bin/$2" && echo "$HOME/.local/bin" >> "${GITHUB_PATH:-/dev/null}"; export PATH="$HOME/.local/bin:$PATH"; }
}

if ! have ffmpeg; then
  python -m pip install -q "imageio-ffmpeg>=0.6" || echo "::warning::imageio-ffmpeg could not be installed"
  link "$(python -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())' 2>/dev/null)" ffmpeg \
    || echo "::warning::imageio-ffmpeg gave no ffmpeg binary"
fi
if ! have ffprobe; then
  dir="${RUNNER_TEMP:-/tmp}/ffprobe-static"
  mkdir -p "$dir"
  npm install --prefix "$dir" --no-audit --no-fund --silent ffprobe-static@3.1.0 || echo "::warning::ffprobe-static could not be installed"
  link "$dir/node_modules/ffprobe-static/bin/linux/x64/ffprobe" ffprobe || echo "::warning::ffprobe-static gave no ffprobe binary"
fi
if ! have ffmpeg || ! have ffprobe; then
  echo "::warning::falling back to apt for ffmpeg"
  for attempt in 1 2; do
    timeout 240 sudo apt-get update -qq -o Acquire::Retries=3 -o Acquire::http::Timeout=30 && break
    echo "::warning::apt-get update attempt $attempt failed"; sleep 5
  done
  timeout 600 sudo apt-get install -y -qq --fix-missing ffmpeg || echo "::warning::apt could not install ffmpeg"
fi
for tool in ffmpeg ffprobe; do
  if have "$tool"; then echo "$tool: $(command -v "$tool") ($("$tool" -version | head -1))"; else echo "::error::$tool is NOT available: films and covers that need it will fail"; fi
done
exit 0
